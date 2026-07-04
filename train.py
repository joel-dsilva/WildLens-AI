import os
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, transforms, models

# =====================================================================
# FaunaIntel AI: Animals-10 CNN Custom Training Pipeline
# Target accuracy: >90% using transfer learning with fine-tuning,
# heavy augmentation, learning rate scheduling, and validation checks.
# =====================================================================

def train_model(dataset_dir, save_path="animals10_model.pth", epochs=15, batch_size=32, lr=0.001):
    print(f"Initializing training pipeline on dataset: {dataset_dir}")

    # -------------------------------------------------------
    # 1. Augmented Training Transforms (key to >90% accuracy)
    # -------------------------------------------------------
    train_transform = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(p=0.1),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
        transforms.RandomRotation(20),
        transforms.RandomGrayscale(p=0.05),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    val_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    # -------------------------------------------------------
    # 2. Data Loader with Train/Val 90/10 Split
    # -------------------------------------------------------
    if not os.path.exists(dataset_dir):
        raise FileNotFoundError(f"Dataset directory '{dataset_dir}' not found.")

    full_dataset = datasets.ImageFolder(root=dataset_dir, transform=train_transform)
    num_classes = len(full_dataset.classes)
    print(f"Detected {num_classes} classes: {full_dataset.classes}")

    # 90% train, 10% validation
    val_size = max(1, int(0.10 * len(full_dataset)))
    train_size = len(full_dataset) - val_size
    train_set, val_set = random_split(full_dataset, [train_size, val_size])

    # Use clean transforms on the validation split
    val_set.dataset = datasets.ImageFolder(root=dataset_dir, transform=val_transform)

    train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True,
                              num_workers=2, pin_memory=True)
    val_loader   = DataLoader(val_set, batch_size=batch_size, shuffle=False,
                              num_workers=2, pin_memory=True)

    # -------------------------------------------------------
    # 3. Model Architecture (MobileNetV3-Large, fine-tuned)
    # -------------------------------------------------------
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    model = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.DEFAULT)

    # Phase 1 — freeze all backbone layers, only train the head
    for param in model.parameters():
        param.requires_grad = False

    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)
    model = model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    # Phase 1 optimizer — head only
    optimizer = optim.AdamW(model.classifier.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    best_val_acc = 0.0
    unfreeze_done = False

    # -------------------------------------------------------
    # 4. Training Loop with staged unfreeze
    # -------------------------------------------------------
    for epoch in range(epochs):

        # Phase 2 — after epoch 5, unfreeze the whole network for fine-tuning
        if epoch == 5 and not unfreeze_done:
            print("\n>> Unfreezing full network for deep fine-tuning...")
            for param in model.parameters():
                param.requires_grad = True
            optimizer = optim.AdamW(model.parameters(), lr=lr * 0.1, weight_decay=1e-4)
            scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs - 5)
            unfreeze_done = True

        # --- Train ---
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0

        for idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()

            if (idx + 1) % 10 == 0 or (idx + 1) == len(train_loader):
                print(f"  Epoch [{epoch+1}/{epochs}] Batch [{idx+1}/{len(train_loader)}] Loss: {loss.item():.4f}")

        epoch_loss = running_loss / train_size
        epoch_acc  = (correct / total) * 100

        # --- Validate ---
        model.eval()
        val_correct = 0
        val_total   = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, predicted = outputs.max(1)
                val_total   += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()

        val_acc = (val_correct / val_total) * 100 if val_total > 0 else 0.0
        scheduler.step()

        print(f"==> Epoch {epoch+1} | Train Loss: {epoch_loss:.4f} | Train Acc: {epoch_acc:.2f}% | Val Acc: {val_acc:.2f}%")

        # Save the best checkpoint
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            state = {
                'model_state': model.state_dict(),
                'classes': full_dataset.classes,
                'best_val_acc': round(best_val_acc, 2),
                'epoch': epoch + 1
            }
            torch.save(state, save_path)
            print(f"   >> New best model saved ({best_val_acc:.2f}% val accuracy)")

    print(f"\nTraining complete. Best validation accuracy: {best_val_acc:.2f}%")
    print(f"Model saved to: {save_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaunaIntel CNN Classifier Trainer — Target >90% Accuracy")
    parser.add_argument("--dataset",    type=str, required=True,              help="Path to Animals-10 dataset directory")
    parser.add_argument("--epochs",     type=int, default=15,                 help="Number of training epochs (default: 15)")
    parser.add_argument("--batch_size", type=int, default=32,                 help="Batch size (default: 32)")
    parser.add_argument("--lr",         type=float, default=0.001,            help="Initial learning rate (default: 0.001)")
    parser.add_argument("--save_path",  type=str, default="animals10_model.pth", help="Output weights path")
    args = parser.parse_args()

    train_model(
        dataset_dir=args.dataset,
        save_path=args.save_path,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr
    )
