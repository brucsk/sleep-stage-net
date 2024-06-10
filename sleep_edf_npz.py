# -*- coding: utf-8 -*-
"""sleep-edf-npz.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1PYyjbiqoVVgLU7ucIbLJPhq7Cr5QUdb-

This notebook is a tutorial to show how to manage the preprocessed data for sleep stage classification
"""

import numpy as np
import gzip as gz
from tqdm.notebook import tqdm
import torch as th
import pickle
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import torch.nn.functional as F
from sklearn.metrics import confusion_matrix, f1_score, ConfusionMatrixDisplay
import time

# Dictionnary with the sleep stages corresponding to the labels 
class_dict = {
    0: "W",
    1: "N1",
    2: "N2",
    3: "N3",
    4: "REM"
}

#datad="/home/allauzen/dev/edf/5-cassette"
datad = "./5-cassette"

#fp = gz.open(datad+'/SC4671G0.npz.gz','rb')
fp = gz.open(datad+'/SC4002E0.npz.gz','rb')
data = np.load(fp,allow_pickle=True)

# To see what it contains
#data.files

# The data are stored in 'x' and 'y'
x = data['x'] # EEG data
y = data['y'] # labels
fs = data['fs'] # sampling rate

#print(x.shape, y.shape, fs)

## Plotting the hypnogram

#time_vect = np.arange(0, x.shape[0], 1)
# Create a plot
plt.plot(y, color = '#62BCE9')

# Set y-axis ticks to graduate every 1 unit
plt.yticks(np.arange(min(y), max(y)+1, 1))
plt.xlabel('Time (s)')
plt.ylabel('Sleep stages')

# Show the plot
plt.show()

# 0 (Wake), 1 (N1), 2 (N2), 3 (N3), 4 (REM) and 5 (Unknown)

# Create a figure and a grid of subplots (4 rows, 1 column)
fig, axs = plt.subplots(4, 1, figsize=(10, 8))

# Plot data on each subplot
axs[0].plot(x[1, :, 1], color = '#62BCE9')
axs[0].set_title('Time segment 1')

axs[1].plot(x[2, :, 1], color = '#62BCE9')
axs[1].set_title('Time segment 2')

axs[2].plot(x[3, :, 1], color = '#62BCE9')
axs[2].set_title('Time segment 3')

axs[3].plot(x[4, :, 1], color = '#62BCE9')
axs[3].set_title('Time segment 4')

# Add labels and grid to each subplot if necessary
for ax in axs:
    ax.set_xlabel('Time')
    ax.set_ylabel('Amplitude')
    ax.grid(True)

# Adjust layout to prevent overlap
plt.tight_layout()

# Display the plot
plt.show()

# The header is the copy of the original one
data["header_raw"]

# The four channels in x are 'EEG Fpz-Cz', 'EEG Pz-Oz', 'EOG horizontal', 'EMG submental'
# You can take more if you modify the preparation script and rerun it.
# To get a list all the files:
import os
import glob
fnames = glob.glob(os.path.join(datad, "*npz.gz"))
print(fnames[:10]) # print the first 10

devpart = 10 #  the data will be split with one part (10%) for validation and nine parts (90%) for training.
xtrain , xvalid = None , None
ytrain , yvalid = None , None
# If you take all the data you dhould end with
#
for fn in tqdm(fnames):
    fp = gz.open(fn,'rb')
    data = np.load(fp,allow_pickle=False) # for now, don't care about headers

    # Extract the channel of interest data and labels
    x = data['x'][:,:,1] # Take either 0: EEG Fpz-Cz; 1: EEg Pz-Oz; 2: EOG 
    y = data['y'] # Take the labels

    # Shuffle the indices to randomize the data
    idx = np.arange(x.shape[0])
    np.random.shuffle(idx)

    # Determine the split point for validation data
    devlim = x.shape[0]//devpart

    # Initialize the training and validation arrays if this is the first iteration
    if xtrain is None:
        xtrain = np.zeros((1,x.shape[1]))
        xvalid = np.zeros((1,x.shape[1]))
        ytrain , yvalid = np.zeros(1) , np.zeros(1)

    # Split and concatenate the data into training and validation sets
    xvalid = np.concatenate((xvalid,x[idx[:devlim]]), axis=0)
    yvalid = np.concatenate((yvalid,y[idx[:devlim]]), axis=0)
    xtrain = np.concatenate((xtrain,x[idx[devlim:]]), axis=0)
    ytrain = np.concatenate((ytrain,y[idx[devlim:]]), axis=0)
    del x,y

print(xtrain.shape, xvalid.shape)
print(ytrain.shape, yvalid.shape)

# clean the first dummy example
xtrain , xvalid = xtrain[1:] , xvalid[1:]
ytrain , yvalid = ytrain[1:] , yvalid[1:]
print(xtrain.shape, xvalid.shape)
print(ytrain.shape, yvalid.shape)

# In Torch version
xtrain, xvalid = th.FloatTensor(xtrain), th.FloatTensor(xvalid)
ytrain, yvalid = th.IntTensor(ytrain), th.IntTensor(yvalid)

outf="./cassette-th-data.pck"
fp = open(outf,"wb")
pickle.dump((xtrain , xvalid , ytrain , yvalid), fp)

#!ls -lh ./cassette-th-data.pck

class SleepStageNet(nn.Module):
    def __init__(self, batch_size, input_dims, n_classes, use_dropout, seq_length, n_rnn_layers, return_last, use_dropout_sequence, name="sleepstagenet"):
        super(SleepStageNet, self).__init__()
        self.batch_size = batch_size
        self.input_dims = input_dims
        self.n_classes = n_classes
        self.use_dropout = use_dropout
        self.seq_length = seq_length
        self.n_rnn_layers = n_rnn_layers
        self.return_last = return_last
        self.use_dropout_sequence = use_dropout_sequence
        self.name = name

        # Define convolutional layers
        self.conv1 = nn.Conv1d(in_channels=1, out_channels=16, kernel_size=5, stride=1, padding=2)
        self.conv2 = nn.Conv1d(in_channels=16, out_channels=32, kernel_size=5, stride=1, padding=2)
        self.pool = nn.MaxPool1d(kernel_size=8, stride=8)

        # Fully connected layers to reduce dimensionality before LSTM
        self.fc1 = nn.Linear(32 * (input_dims // 64), 1024)
        self.fc2 = nn.Linear(1024, 32)  # Adjust to match LSTM input size

        # Dropout for regularization
        self.dropout = nn.Dropout(p=0.5)

        # LSTM layer with 512 hidden units
        self.rnn = nn.LSTM(input_size=32, hidden_size=512, num_layers=n_rnn_layers, bidirectional=True, batch_first=True)

        # Final fully connected layer to map LSTM output to class probabilities
        self.fc3 = nn.Linear(512 * 2, n_classes)

    def forward(self, x):
        # Apply convolutional layers with activation and pooling
        x = F.relu(self.conv1(x))
        x = self.pool(x)
        x = F.relu(self.conv2(x))
        x = self.pool(x)

        # Flatten the output for the fully connected layers
        x = torch.flatten(x, 1)
        #print("Shape after flattening:", x.shape)

        # Apply fully connected layers with dropout
        x = F.relu(self.fc1(x))
        if self.use_dropout:
            x = self.dropout(x)
        #print("Shape after fc1 and dropout:", x.shape)

        # Apply the second fully connected layer to match LSTM input size
        x = F.relu(self.fc2(x))
        #print("Shape after fc2:", x.shape)

        # Reshape for LSTM input
        x = x.view(-1, self.seq_length, 32)  # Adjust view to match LSTM input size
        #print("Shape before RNN:", x.shape)

        # Apply LSTM
        out, _ = self.rnn(x)
        #print(f"Shape after RNN: {out.shape}")

        if self.return_last:
            out = out[:, -1, :]
        else:
            out = out.contiguous().view(-1, 512 * 2)

        # Apply final fully connected layer
        x = self.fc3(out)
        return x

def train(model, Xtrain, Ytrain, Xvalid, Yvalid, device, epochs=150, verbose=False, lr=0.000001, batch_size=30):
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.CrossEntropyLoss()

    # Ensure the target tensors are of type LongTensor
    Ytrain = torch.LongTensor(Ytrain.numpy()) if isinstance(Ytrain, torch.Tensor) else torch.LongTensor(Ytrain)
    Yvalid = torch.LongTensor(Yvalid.numpy()) if isinstance(Yvalid, torch.Tensor) else torch.LongTensor(Yvalid)

    # Create DataLoader for training and validation datasets
    train_dataset = TensorDataset(Xtrain, Ytrain)
    valid_dataset = TensorDataset(Xvalid, Yvalid)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    valid_loader = DataLoader(valid_dataset, batch_size=batch_size, shuffle=False)

    train_losses, valid_losses, valid_accuracies = [], [], []
    
    start_time = time.time()  # Record the start time

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        total_train_samples = 0

        for images, labels in tqdm(train_loader):
            images, labels = images.to(device), labels.to(device)

            optimizer.zero_grad()
            outputs = model(images)

            # Ensure the outputs and labels have the same batch size
            if outputs.size(0) != labels.size(0):
                raise ValueError(f"Expected input batch_size ({outputs.size(0)}) to match target batch_size ({labels.size(0)}).")

            loss = loss_fn(outputs, labels)
            loss.backward()
            optimizer.step()

            running_loss += loss.item() * images.size(0)
            total_train_samples += images.size(0)

        train_losses.append(running_loss / total_train_samples)

        model.eval()
        valid_loss = 0.0
        correct_predictions = 0
        total_valid_samples = 0
        y_pred = []
        y_true = []

        with torch.no_grad():
            for images, labels in tqdm(valid_loader):
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)

                # Ensure the outputs and labels have the same batch size
                if outputs.size(0) != labels.size(0):
                    raise ValueError(f"Expected input batch_size ({outputs.size(0)}) to match target batch_size ({labels.size(0)}).")

                loss = loss_fn(outputs, labels)
                valid_loss += loss.item() * images.size(0)

                _, predicted = torch.max(outputs, 1)
                correct_predictions += (predicted == labels).sum().item()
                total_valid_samples += images.size(0)
                y_pred.extend(predicted.cpu().numpy())
                y_true.extend(labels.cpu().numpy())

        valid_losses.append(valid_loss / total_valid_samples)
        valid_accuracies.append(100 * correct_predictions / total_valid_samples)

        if verbose:
            print(f"Epoch {epoch+1}/{epochs}")
            print(f"Train Loss: {train_losses[-1]:.4f}")
            print(f"Valid Loss: {valid_losses[-1]:.4f}")
            print(f"Valid Accuracy: {valid_accuracies[-1]:.2f}%")
            
    end_time = time.time()  # Record the end time
    total_time = end_time - start_time  # Calculate the total training time

    return train_losses, valid_losses, valid_accuracies, y_true, y_pred, total_time

def plotMetrics(class_dict,train_losses, valid_losses, valid_accuracies, y_true, y_pred, normalize='true'):
    
    # Plot train losses, valid losses and accuracy 
    plt.figure(figsize=(9, 1.5))
    plt.subplot(1, 3, 1)
    plt.plot(train_losses)
    plt.title("Train Loss")
    plt.xlabel("Epochs")
    plt.subplot(1, 3, 2)
    plt.plot(valid_losses)
    plt.title("Valid Loss")
    plt.xlabel("Epochs")
    plt.subplot(1, 3, 3)
    plt.plot(valid_accuracies)
    plt.title("Valid Accuracy")
    plt.xlabel("Epochs")
    plt.show()
    
    # Normalize confusion matrix
    cm = confusion_matrix(y_true, y_pred, normalize=normalize)
    # Display confusion matrix with class labels and custom colormap
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=[class_dict[i] for i in range(len(class_dict))])
    disp.plot(cmap='inferno', ax=plt.gca())
    plt.title("Confusion Matrix")
    plt.show
    
    
 
# Parameters
batch_size = 10
input_dims = 600  # Each sample has 600 features
n_classes = len(torch.unique(ytrain))  # Number of unique classes in the target
seq_length = 1  # Since each input is an individual sample, seq_length is 1
n_rnn_layers = 1
return_last = True
use_dropout = True
use_dropout_sequence = True

# Instantiate model
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = SleepStageNet(
    batch_size=batch_size,
    input_dims=input_dims,
    n_classes=n_classes,
    use_dropout=use_dropout,
    seq_length=seq_length,
    n_rnn_layers=n_rnn_layers,
    return_last=return_last,
    use_dropout_sequence=use_dropout_sequence
).to(device)

# Ensure the data is in the correct shape
Xtrain = xtrain.unsqueeze(1)  # Shape (num_samples, 1, 600)
Xvalid = xvalid.unsqueeze(1)  # Shape (num_samples, 1, 600)
Ytrain = ytrain
Yvalid = yvalid

print(Xtrain.shape, Ytrain.shape, Xvalid.shape, Yvalid.shape)

# Train the model
train_losses, valid_losses, valid_accuracies, y_true, y_pred, total_time = train(model, Xtrain, Ytrain, Xvalid, Yvalid, epochs=150, verbose=True, lr=0.000001, batch_size=10, device=device)

plotMetrics(class_dict,train_losses, valid_losses, valid_accuracies, y_true, y_pred, normalize='true')