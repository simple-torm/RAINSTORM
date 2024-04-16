"""
Created on Tue Nov  7 16:59:14 2023

@author: dhers

This script will train a model that classifies positions into exploration
"""

#%% Import libraries

import h5py
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import random

# from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import accuracy_score, precision_score, classification_report, recall_score, f1_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier

import tensorflow as tf
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.callbacks import EarlyStopping, LearningRateScheduler

print(tf.config.list_physical_devices('GPU'))

import cv2
from moviepy.editor import VideoFileClip
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import joblib


import seaborn as sns
from sklearn.metrics import jaccard_score
from sklearn.metrics.pairwise import cosine_similarity

import datetime

#%% Set the variables before starting

# At home:
desktop = 'C:/Users/dhers/Desktop'

# At the lab:
# desktop = '/home/usuario/Desktop'

STORM_folder = os.path.join(desktop, 'STORM')
colabels_file = os.path.join(STORM_folder, 'colabeled_data_2.csv')

before = 1 # Say how many frames into the past the models will see
after = 1 # Say how many frames into the future the models will see

frames = before + after + 1

# Set the number of neurons in each layer
param_0 = 48 # 3x las columnas de entrada (16)
param_H1 = 40
param_H2 = 32
param_H3 = 24
param_H4 = 16

batch_size = 2048 # Set the batch size
epochs = 100 # Set the training epochs

patience = 10 # Set the wait for the early stopping mechanism

use_saved_data = False # if True, we use the dataframe processed previously

if use_saved_data:
    saved_data = 'saved_training_data.h5'

else:
    focus = False # if True, the data processing will remove unimportant moments
    save_data = False # if True, the data processed will be saved with today's date

#%% Start time

# Get the start time
start_time = datetime.datetime.now()

#%% Results

"""
"""

#%% Function to smooth the columns (filter 2 or less individual occurrences)

def smooth_column(data_array):
    smoothed_columns = []
    for i in range(2):  # Loop through both columns
        smoothed_column = data_array[:, i].copy()
        changes = 0
        for j in range(1, len(smoothed_column) - 1):
            # Smooth occurrences with fewer than 3 consecutive 1s or 0s
            if (smoothed_column[j - 1] == smoothed_column[j + 1] or 
                (j > 1 and smoothed_column[j - 2] == smoothed_column[j + 1]) or
                (j < len(smoothed_column) - 2 and smoothed_column[j - 1] == smoothed_column[j + 2])) and \
                smoothed_column[j] != smoothed_column[j - 1]:
                smoothed_column[j] = smoothed_column[j - 1]
                changes += 1
        
        smoothed_columns.append(smoothed_column)
        print(f"Number of changes in column {i}: {changes}")
        
    smoothed_array = np.column_stack(smoothed_columns)
    return smoothed_array

#%% Function to focus on the most important video parts

def remove_sparse_rows(df):
    # Initialize a list to store indices of rows to be removed
    rows_to_remove = []

    # Iterate through the dataframe
    for i in range(len(df)):
        # Check if the last two columns have a 1 in at least 10 rows prior and after the current row
        if (df.iloc[max(0, i - 10):i, -2:] == 0).all().all() and (df.iloc[i + 1:i + 11, -2:] == 0).all().all():
            rows_to_remove.append(i)

    # Drop the rows from the dataframe
    df_cleaned = df.drop(rows_to_remove)
    print(f'Removed {len(rows_to_remove)} rows')

    return df_cleaned

#%% This function prepares data for training, testing and validating

def divide_training_data(df):

    unique_values = df.iloc[:, 0].unique()
    unique_values_list = unique_values.tolist()

    # Calculate the number of elements to select (30% of the list)
    percentage = int(len(unique_values_list) * 0.3)
    
    # Randomly select 10% of the numbers
    selection = random.sample(unique_values_list, percentage)
    
    # Split the list into two halves
    selection_test = selection[:len(selection) // 2]
    selection_val = selection[len(selection) // 2:]
    
    # Create a new dataframe 'test' with rows from 'df' that start with the selected numbers
    test = df[df.iloc[:, 0].astype(str).str.startswith(tuple(map(str, selection_test)))]
    val = df[df.iloc[:, 0].astype(str).str.startswith(tuple(map(str, selection_val)))]
    
    # Remove the selected rows from the original dataframe 'df'
    df = df[~df.iloc[:, 0].astype(str).str.startswith(tuple(map(str, selection)))]
    
    return df, test, val

#%% Lets load the data

if use_saved_data:
    # Load arrays
    with h5py.File(saved_data, 'r') as hf:
        X_test = hf['X_test'][:]
        y_test = hf['y_test'][:]
        X_val = hf['X_val'][:]
        y_val = hf['y_val'][:]
        X_train = hf['X_train'][:]
        y_train = hf['y_train'][:]
        
    print("Data is ready to train")

else:
    print("Data is NOT ready to train")
    
    colabels = pd.read_csv(colabels_file)
    
    train, test, val = divide_training_data(colabels)

    # Define features (X) and target (y) columns
    X_train = train.iloc[:, :18]  # Position
    y_train_float = train.iloc[:, 22:24]  # Labels
    y_train = (y_train_float > 0.6).astype(int)
    
    X_test = test.iloc[:, :18]
    y_test_float = test.iloc[:, 22:24]
    y_test = (y_test_float > 0.6).astype(int)

    X_val = val.iloc[:, :18]
    y_val_float = val.iloc[:, 22:24]
    y_val = (y_val_float > 0.6).astype(int)

    # Print the sizes of each set
    print(f"Training set size: {len(X_train)} samples")
    print(f"Validation set size: {len(X_val)} samples")
    print(f"Testing set size: {len(X_test)} samples")
    
    print("Data is now ready to train")

    if save_data:
        # Save arrays
        with h5py.File(f'saved_training_data_{start_time.date()}.h5', 'w') as hf:
            hf.create_dataset('X_test', data=X_test)
            hf.create_dataset('y_test', data=y_test)
            hf.create_dataset('X_val', data=X_val)
            hf.create_dataset('y_val', data=y_val)
            hf.create_dataset('X_train', data=X_train)
            hf.create_dataset('y_train', data=y_train)
            
            print(f'Saved data to saved_training_data_{start_time.date()}.h5')

#%%

"""
Lets get some tools ready for model training:
    early stopping
    scheduled learning rate
"""

#%% Define the EarlyStopping callback

early_stopping = EarlyStopping(
    monitor='val_loss',
    patience=patience,
    restore_best_weights=True,
    mode='min',
    verbose=1,
)

#%% Define a learning rate schedule function

initial_lr = 0.001 # Set the initial lr

# Define a learning rate schedule function
def lr_schedule(epoch):
    initial_lr = 0.001  # Initial learning rate
    decay_factor = 0.9  # Learning rate decay factor
    decay_epochs = 5    # Number of epochs after which to decay the learning rate

    # Calculate the new learning rate
    lr = initial_lr * (decay_factor ** (epoch // decay_epochs))

    return lr

# Define the LearningRateScheduler callback
lr_scheduler = LearningRateScheduler(lr_schedule)

#%%

def plot_history(model, model_name):
    
    plt.figure(figsize=(10, 6))
    
    plt.plot(model.history['loss'], label='Training loss')
    plt.plot(model.history['val_loss'], label='Validation loss')
    plt.plot(model.history['accuracy'], label='Training accuracy')
    plt.plot(model.history['val_accuracy'], label='Validation accuracy')
    
    plt.title(model_name)
    plt.xlabel('Epochs')
    plt.ylabel('%')
    plt.legend()
    plt.show()
    
#%%

def evaluate(X, y, model):
    
    # Evaluate the model on the testing set
    y_pred = model.predict(X)
    y_pred_binary = (y_pred > 0.5).astype(int)  # Convert probabilities to binary predictions
    # y_pred_binary = smooth_column(y_pred_binary)

    accuracy = accuracy_score(y, y_pred_binary)
    precision = precision_score(y, y_pred_binary, average = 'weighted')
    recall = recall_score(y, y_pred_binary, average = 'weighted')
    f1 = f1_score(y, y_pred_binary, average = 'weighted')
    
    print(classification_report(y, y_pred_binary))
    
    return accuracy, precision, recall, f1

#%%

"""
Now we train the first model
"""

#%% Define a simple model

# Build a simple neural network
model_simple = tf.keras.Sequential([
    Dense(param_0, activation='relu', input_shape=(X_train.shape[1],)),
    Dense(param_H1, activation='relu'),
    Dense(param_H2, activation='relu'),
    Dense(param_H3, activation='relu'),
    Dense(param_H4, activation='relu'),
    Dense(2, activation='sigmoid')
])

# Compile the model
model_simple.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=initial_lr),
                     loss='binary_crossentropy', metrics=['accuracy'])

model_simple.summary()

#%% Train the model

history_simple = model_simple.fit(X_train, y_train,
                              epochs = epochs,
                              batch_size = batch_size,
                              validation_data=(X_val, y_val),
                              callbacks=[early_stopping, lr_scheduler])

#%% Calculate accuracy and precision of the model

accuracy_simple, precision_simple, recall_simple, f1_simple = evaluate(X_test, y_test, model_simple)
print(f"Accuracy = {accuracy_simple:.4f}, Precision = {precision_simple:.4f}, Recall = {recall_simple:.4f}, F1 Score = {f1_simple:.4f} -> simple")

#%%

"""
Lets move onto training a Recursive Network (that can see sequences)
"""

#%% This function reshapes data for LSTM models

"""
Implement LSTM models that can take into account the frames previous to exploration
    - First we need to reshape the dataset to look at more than one row for one output
"""

def reshape_set(data, labels, back, forward):
    
    if labels is False:
        
        if isinstance(data, pd.DataFrame):
            data = data.to_numpy()
        
        reshaped_data = []
    
        for i in range(back, len(data) - forward):
            reshaped_data.append(data[i - back : 1 + i + forward])
        
        # Calculate the number of removed rows
        removed_rows = len(data) - len(reshaped_data)
        
        print(f"Reshaping removed {removed_rows} rows")
        
        reshaped_data_tf = tf.convert_to_tensor(reshaped_data, dtype=tf.float64)
    
        return reshaped_data_tf
        
    else:
        
        if isinstance(data, pd.DataFrame):
            data = data.to_numpy()
        if isinstance(labels, pd.DataFrame):
            labels = labels.to_numpy()
        
        reshaped_data = []
        reshaped_labels = []
    
        for i in range(back, len(data) - forward):
            if data[i - back, 0] == data[i, 0] == data[i + forward, 0]:
                reshaped_data.append(data[i - back : 1 + i + forward])
                reshaped_labels.append(labels[i])
        
        # Calculate the number of removed rows
        removed_rows = len(data) - len(reshaped_data)
        
        print(f"Reshaping removed {removed_rows} rows")
        
        reshaped_data_tf = tf.convert_to_tensor(reshaped_data, dtype=tf.float64)
        reshaped_labels_tf = tf.convert_to_tensor(reshaped_labels, dtype=tf.float64)
    
        return reshaped_data_tf, reshaped_labels_tf

#%% Prepare the wide data

# Reshape the training set
X_train_seq, y_train_seq = reshape_set(X_train, y_train, before, after)

# Reshape the testing set
X_test_seq, y_test_seq = reshape_set(X_test, y_test, before, after)

# Reshape the validating set
X_val_seq, y_val_seq = reshape_set(X_val, y_val, before, after)

#%% Define a first LSTM model

# Build a LSTM-based neural network
model_wide = tf.keras.Sequential([
    LSTM(param_0, input_shape=(frames, X_train_seq.shape[2]), return_sequences = True),
    LSTM(param_H1, return_sequences = True),
    LSTM(param_H2, return_sequences = True),
    LSTM(param_H3, return_sequences = True),
    LSTM(param_H4),
    Dense(2, activation='sigmoid')
])

# Compile the model
model_wide.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=initial_lr),
                     loss='binary_crossentropy', metrics=['accuracy'])
model_wide.summary()

#%% Train the model

history_wide = model_wide.fit(X_train_seq, y_train_seq,
                              epochs = epochs,
                              batch_size = batch_size,
                              validation_data=(X_val_seq, y_val_seq),
                              callbacks=[early_stopping, lr_scheduler])

#%% Calculate accuracy and precision of the model

accuracy_wide, precision_wide, recall_wide, f1_wide = evaluate(X_test_seq, y_test_seq, model_wide)
print(f"Accuracy = {accuracy_wide:.4f}, Precision = {precision_wide:.4f}, Recall = {recall_wide:.4f}, F1 Score = {f1_wide:.4f} -> wide")

#%%

"""
Lets also Load a pretrained RF model
"""

#%% Load a pretrained model

multi_output_old_model = joblib.load(os.path.join(STORM_folder, 'trained_model_203.pkl'))

#%% Calculate accuracy and precision of the model

accuracy_old, precision_old, recall_old, f1_old = evaluate(X_test, y_test, multi_output_old_model)
print(f"Accuracy = {accuracy_old:.4f}, Precision = {precision_old:.4f}, Recall = {recall_old:.4f}, F1 Score = {f1_old:.4f} -> RF old")

#%%

"""
Now we can use the models in an example video
"""

#%% Prepare the dataset of a video we want to analyze and see

position_df = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_position.csv'))
video_path = os.path.join(STORM_folder, 'Example/Example_video.mp4')

labels_agus = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_Agus.csv'), usecols=['Left', 'Right'])
labels_marian = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_Marian.csv'), usecols=['Left', 'Right'])
labels_santi = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_Santi.csv'), usecols=['Left', 'Right'])
labels_dhers = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_Dhers.csv'), usecols=['Left', 'Right'])
labels_old = pd.read_csv(os.path.join(STORM_folder, 'Example/Example_old.csv'), usecols=['Left', 'Right'])

colabels = (labels_agus + labels_marian + labels_santi + labels_dhers) / 4

#%%
    
X_view = position_df[['obj_1_x', 'obj_1_y', 'obj_2_x', 'obj_2_y',
                'nose_x', 'nose_y', 'L_ear_x', 'L_ear_y',
                'R_ear_x', 'R_ear_y', 'head_x', 'head_y',
                'neck_x', 'neck_y', 'body_x', 'body_y', 'tail_1_x', 'tail_1_y']].values

# Extract labels (exploring or not)
y_view = (colabels > 0.5).astype(int)

#%% Predict the simple labels

autolabels_simple = model_simple.predict(X_view)

autolabels_simple_binary = (autolabels_simple > 0.5).astype(int) 
# autolabels_simple_binary = smooth_column(np.array(autolabels_simple_binary))
autolabels_simple_binary = pd.DataFrame(autolabels_simple_binary, columns=["Left", "Right"])
# autolabels_simple_binary.insert(0, "Frame", autolabels_simple_binary.index + 1)

autolabels_simple = pd.DataFrame(autolabels_simple, columns=["Left", "Right"])
# autolabels_simple.insert(0, "Frame", autolabels_simple.index + 1)

#%% Predict the wide_1 labels

position_seq = reshape_set(X_view, False, before, after)

autolabels_wide = model_wide.predict(position_seq)
autolabels_wide = np.vstack((np.zeros((before, 2)), autolabels_wide))
autolabels_wide = np.vstack((autolabels_wide, np.zeros((after, 2))))

autolabels_wide_binary = (autolabels_wide > 0.5).astype(int)
# autolabels_wide_1_binary = smooth_column(np.array(autolabels_wide_1_binary))
autolabels_wide_binary = pd.DataFrame(autolabels_wide_binary, columns=["Left", "Right"])
# autolabels_wide_binary.insert(0, "Frame", autolabels_wide_binary.index + 1)

autolabels_wide = pd.DataFrame(autolabels_wide, columns=["Left", "Right"])
# autolabels_wide_1.insert(0, "Frame", autolabels_wide_1.index + 1)

#%% Predict the RF labels

autolabels_old = multi_output_old_model.predict(X_view)
# autolabels_old = smooth_column(np.array(autolabels_old))
autolabels_old = pd.DataFrame(autolabels_old, columns=["Left", "Right"])
# autolabels_old.insert(0, "Frame", autolabels_old.index + 1)

#%% Prepare the manual labels

autolabels_manual = pd.DataFrame(y_view, columns=["Left", "Right"])

#%%

"""
We can now visualize the model results
"""

#%% Lets plot the timeline to see the performance of the model

plt.switch_backend('QtAgg')

plt.figure(figsize = (16, 6))

plt.plot(autolabels_manual["Left"] * 1, ".", color = "black", label = "Manual")
plt.plot(autolabels_manual["Right"] * -1, ".", color = "black")

plt.plot(autolabels_old["Left"] * 1.025, ".", color = "y", label = "RF_Old")
plt.plot(autolabels_old["Right"] * -1.025, ".", color = "y")

plt.plot(autolabels_simple["Left"], color = "r")
plt.plot(autolabels_simple["Right"] * -1, color = "r")
plt.plot(autolabels_simple_binary["Left"] * 1.050, ".", color = "r", label = "autolabels_simple")
plt.plot(autolabels_simple_binary["Right"] * -1.050, ".", color = "r")

plt.plot(autolabels_wide["Left"], color = "g")
plt.plot(autolabels_wide["Right"] * -1, color = "g")
plt.plot(autolabels_wide_binary["Left"] * 1.075, ".", color = "g", label = "autolabels_wide")
plt.plot(autolabels_wide_binary["Right"] * -1.075, ".", color = "g")

plt.plot(colabels["Left"], color = "black", linewidth = 2)
plt.plot(colabels["Right"] * -1, color = "black", linewidth = 2)

plt.plot(labels_marian["Left"] * 1.125, ".", color = "m", label = "Marian")
plt.plot(labels_marian["Right"] * -1.125, ".", color = "m")

plt.plot(labels_agus["Left"] * 1.150, ".", color = "c", label = "Agus")
plt.plot(labels_agus["Right"] * -1.150, ".", color = "c")

plt.plot(labels_santi["Left"] * 1.175, ".", color = "orange", label = "Santi Ojea")
plt.plot(labels_santi["Right"] * -1.175, ".", color = "orange")

plt.plot(labels_dhers["Left"] * 1.200, ".", color = "b", label = "Santi Dhers")
plt.plot(labels_dhers["Right"] * -1.200, ".", color = "b")

"""
plt.plot(autolabels_RF["Left"] * 1.05, ".", color = "gray", label = "RF")
plt.plot(autolabels_RF["Right"] * -1.05, ".", color = "gray")

plt.plot(autolabels_sides["Left"], color = "g")
plt.plot(autolabels_sides["Right"] * -1, color = "g")
plt.plot(autolabels_sides_binary["Left"] * 1.2, ".", color = "g", label = "autolabels_sides")
plt.plot(autolabels_sides_binary["Right"] * -1.2, ".", color = "g")
"""

# Zoom in on the labels and the minima of the distances and angles
plt.ylim((-1.3, 1.3))
plt.axhline(y=0.5, color='black', linestyle='--')
plt.axhline(y=-0.5, color='black', linestyle='--')

plt.legend()
plt.show()

#%% Get the end time

end_time = datetime.datetime.now()

# Calculate elapsed time
elapsed_time = end_time - start_time

#%% Plot the training and validation loss
    
plot_history(history_simple, "Simple")
plot_history(history_wide, "wide")

"""
plot_history(history_left, "Left")
plot_history(history_right, "Right")
"""

#%% Print the model results

print(f"Script execution time: {elapsed_time}).")

# print(f"Accuracy = {accuracy_RF:.4f}, Precision = {precision_RF:.4f}, Recall = {recall_RF:.4f}, F1 Score = {f1_RF:.4f} -> RF")

print("Evaluate over testing data")

print(f"Accuracy = {accuracy_old:.4f}, Precision = {precision_old:.4f}, Recall = {recall_old:.4f}, F1 Score = {f1_old:.4f} -> old")

print(f"Accuracy = {accuracy_simple:.4f}, Precision = {precision_simple:.4f}, Recall = {recall_simple:.4f}, F1 Score = {f1_simple:.4f} -> simple")

print(f"Accuracy = {accuracy_wide:.4f}, Precision = {precision_wide:.4f}, Recall = {recall_wide:.4f}, F1 Score = {f1_wide:.4f} -> wide")

# print(f"Accuracy = {accuracy_sides:.4f}, Precision = {precision_sides:.4f}, Recall = {recall_sides:.4f}, F1 Score = {f1_sides:.4f} -> sides")

#%%

print("Evaluate over viewing data")

labelers = [autolabels_old, autolabels_simple_binary, autolabels_wide_binary, labels_agus, labels_marian, labels_santi, labels_dhers]
labelers_names = ['old', 'simple', 'wide', 'labels_agus', 'labels_marian', 'labels_santi', 'labels_dhers']

for i, labeler in enumerate(labelers):
    accuracy = accuracy_score(labeler, autolabels_manual)
    precision = precision_score(labeler, autolabels_manual, average='weighted')
    recall = recall_score(labeler, autolabels_manual, average='weighted')
    f1 = f1_score(labeler, autolabels_manual, average='weighted')

    # Print evaluation metrics along with the labeler's name
    print(f"Accuracy = {accuracy:.4f}, Precision = {precision:.4f}, Recall = {recall:.4f}, F1 Score = {f1:.4f} -> {labelers_names[i]}")

#%%

"""
Lets see how similar the labels are to each other
"""

#%%

df = pd.DataFrame()

df["old"] = autolabels_old["Left"] + autolabels_old["Right"]
df["simple"] = autolabels_simple_binary["Left"] + autolabels_simple_binary["Right"]
df["wide"] = autolabels_wide_binary["Left"] + autolabels_wide_binary["Right"]

df["Marian"] = labels_marian["Left"] + labels_marian["Right"]
df["Agus"] = labels_agus["Left"] + labels_agus["Right"]
df["Santi"] = labels_santi["Left"] + labels_santi["Right"]
df["Dhers"] = labels_dhers["Left"] + labels_dhers["Right"]

#%% Compute Cosine similarity

cosine_sim = pd.DataFrame(cosine_similarity(df.T), index=df.columns, columns=df.columns)

print("\nCosine Similarity:")
print(cosine_sim)

#%% Plot Cosine similarity heatmap

plt.figure(figsize=(8, 6))
sns.heatmap(cosine_sim.astype(float), annot=True, cmap="coolwarm", fmt=".2f")
plt.title("Cosine Similarity")
plt.show()

#%%

from sklearn.decomposition import PCA

# Use PCA for dimensionality reduction to 2 components
pca = PCA(n_components=2)
pca_result = pca.fit_transform(cosine_sim)

# Plot the 2D representation
plt.figure(figsize=(8, 6))
plt.scatter(pca_result[:, 0], pca_result[:, 1])

# Annotate the points with column names
for i, column in enumerate(df.columns):
    plt.annotate(column, (pca_result[i, 0], pca_result[i, 1]))

plt.title("PCA Visualization of Column Similarity")
plt.xlabel("Principal Component 1")
plt.ylabel("Principal Component 2")
plt.grid(True)
plt.show()

#%% Define a function that allows us to visualize the labels together with the video

def process_frame(frame, frame_number):
    
    move = False
    leave = False

    # Plot using Matplotlib with Agg backend
    fig, ax = plt.subplots(figsize=(6, 4))
    
    ax.plot(autolabels_manual["Left"] * 1, ".", color = "black", label = "Manual")
    ax.plot(autolabels_manual["Right"] * -1, ".", color = "black")
    
    ax.plot(autolabels_simple["Left"], color = "r")
    ax.plot(autolabels_simple["Right"] * -1, color = "r")
    
    ax.plot(autolabels_wide["Left"], color = "b")
    ax.plot(autolabels_wide["Right"] * -1, color = "b")
    
    """
    ax.plot(autolabels_sides["Left"], color = "g")
    ax.plot(autolabels_sides["Right"] * -1, color = "g")
    """
    
    
    ax.set_xlim(frame_number-5, frame_number+5)
    ax.set_ylim(-1.5, 1.5)
    ax.axvline(x=frame_number, color='black', linestyle='--')
    ax.axhline(y=0.5, color='black', linestyle='--')
    ax.axhline(y=-0.5, color='black', linestyle='--')
    
    ax.set_title(f'Plot for Frame {frame_number}')
    ax.set_xlabel('X-axis')
    ax.set_ylabel('Y-axis')
    ax.grid=True

    # Save the plot as an image in memory
    plot_img_path = 'plot_img.png'
    canvas = FigureCanvas(fig)
    canvas.print_png(plot_img_path)
    
    # Load the saved plot image
    plot_img = cv2.imread(plot_img_path)
    
    # Resize the plot image to match the height of the frame
    plot_img = cv2.resize(plot_img, (frame.shape[1], frame.shape[0]))
    
    # Combine the frame and plot images horizontally
    combined_img = np.concatenate((frame, plot_img), axis=1)

    # Display the combined image
    cv2.imshow("Frame with Plot", combined_img)

    # Wait for a keystroke
    key = cv2.waitKey(0)
    
    if key == ord('6'):
        move = 1
    if key == ord('4'):
        move = -1
    if key == ord('9'):
        move = 5
    if key == ord('7'):
        move = -5
    if key == ord('3'):
        move = 50
    if key == ord('1'):
        move = -50
    if key == ord('q'):
        leave = True
    
    return move, leave

def visualize_video_frames(video_path):
    
    video = VideoFileClip(video_path)
    
    frame_generator = video.iter_frames()
    frame_list = list(frame_generator) # This takes a while
    
    # Switch Matplotlib backend to Agg temporarily
    original_backend = plt.get_backend()
    plt.switch_backend('Agg')
    
    current_frame = 0 # Starting point of the video
    leave = False
    
    while current_frame < len(frame_list) and not leave:
              
        frame = frame_list[current_frame] # The frame we are labeling
        
        # Process the current frames
        move, leave = process_frame(frame, current_frame)
        
        if move: # Move some frames
            if 0 < (current_frame + move) < len(frame_list):
                current_frame += move
                
    
    # Revert Matplotlib backend to the original backend
    plt.switch_backend(original_backend)
    
    # Close the OpenCV windows
    cv2.destroyAllWindows()

#%%

# visualize_video_frames(video_path)

#%%

"""
# Save arrays
with h5py.File('saved_training_data.h5', 'w') as hf:
    hf.create_dataset('X_test', data=X_test)
    hf.create_dataset('y_test', data=y_test)
    hf.create_dataset('X_val', data=X_val)
    hf.create_dataset('y_val', data=y_val)
    hf.create_dataset('X_train', data=X_train)
    hf.create_dataset('y_train', data=y_train)
    # ... Save other arrays


#%%

initial_lr = 0.001 # Set the initial lr

# Define a learning rate schedule function
def lr_schedule(epoch):
    initial_lr = 0.001  # Initial learning rate
    decay_factor = 0.9  # Learning rate decay factor
    decay_epochs = 5    # Number of epochs after which to decay the learning rate

    # Calculate the new learning rate
    lr = initial_lr * (decay_factor ** (epoch // decay_epochs))

    return lr

# Define the LearningRateScheduler callback
lr_scheduler = LearningRateScheduler(lr_schedule)

#%% Compute class weights

class_weight_left = compute_class_weight('balanced', classes=[0, 1], y = y_train[:, 0])
class_weight_right = compute_class_weight('balanced', classes=[0, 1], y = y_train[:, 1])

# Calculate the average frequency of exploration
freq_exp = (class_weight_left[0] + class_weight_right[0]) / 2 # Calculate the average frequency of exploration
freq_else = (class_weight_left[1] + class_weight_right[1]) / 2

# Create dictionaries for class weights for each output column
class_weight_dict = {0: freq_exp, 1: freq_exp}
"""
#%%

"""
import torch
import torch.nn as nn

class WideLSTM(nn.Module):
    def __init__(self):
        super(WideLSTM, self).__init__()
        self.lstm1 = nn.LSTM(input_size=16, hidden_size=48, batch_first=True)
        self.lstm2 = nn.LSTM(input_size=48, hidden_size=40, batch_first=True)
        self.lstm3 = nn.LSTM(input_size=40, hidden_size=32, batch_first=True)
        self.lstm4 = nn.LSTM(input_size=32, hidden_size=24, batch_first=True)
        self.lstm5 = nn.LSTM(input_size=24, hidden_size=16, batch_first=True)
        self.fc = nn.Linear(16, 2)
        self.activation = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        out, _ = self.lstm1(x)
        out = self.activation(out)
        out, _ = self.lstm2(out)
        out = self.activation(out)
        out, _ = self.lstm3(out)
        out = self.activation(out)
        out, _ = self.lstm4(out)
        out = self.activation(out)
        out, _ = self.lstm5(out)
        out = torch.squeeze(out[:, -1, :], dim=1)  # Flatten the output of the last LSTM layer
        out = self.fc(out)
        out = self.sigmoid(out)
        return out

# Create an instance of the model
model_wide_pytorch = WideLSTM()

print(model_wide_pytorch)


#%% Define a second LSTM model dividing Left and Right

def create_model():
    model = tf.keras.Sequential([
        LSTM(param_0, input_shape=(frames, X_train_seq.shape[2]), return_sequences = True),
        LSTM(param_H1, return_sequences = True),
        LSTM(param_H2, return_sequences = True),
        LSTM(param_H3, return_sequences = True),
        LSTM(param_H4),
        Dense(1, activation='sigmoid')
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=initial_lr),
                  loss='binary_crossentropy', metrics=['accuracy'])
    return model

def train_model(model, X_train, y_train, X_val, y_val):
    history = model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size,
                        validation_data=(X_val, y_val), callbacks=[early_stopping, lr_scheduler])
    return history

#%%

#Prepare the data by side
y_test_left = y_test_seq[:, 0]
y_test_right = y_test_seq[:, 1]

y_val_left = y_val_seq[:, 0]
y_val_right = y_val_seq[:, 1]

y_train_left = y_train_seq[:, 0]
y_train_right = y_train_seq[:, 1]

# Create left and right models
model_left = create_model()
model_right = create_model()

# Train left and right models
history_left = train_model(model_left, X_train_seq, y_train_left, X_val_seq, y_val_left)
history_right = train_model(model_right, X_train_seq, y_train_right, X_val_seq, y_val_right)

#%% Calculate accuracy and precision of the model

# Evaluate the model on the testing set
y_pred_left = model_left.predict(X_test_seq)
y_pred_right = model_right.predict(X_test_seq)

y_pred_sides = np.hstack((y_pred_left, y_pred_right))
y_pred_binary_sides = (y_pred_sides > 0.5).astype(int)  # Convert probabilities to binary predictions
# y_pred_binary_sides = smooth_column(y_pred_binary_sides)

accuracy_sides = accuracy_score(y_test_seq, y_pred_binary_sides)
precision_sides = precision_score(y_test_seq, y_pred_binary_sides, average = 'weighted')
recall_sides = recall_score(y_test_seq, y_pred_binary_sides, average = 'weighted')
f1_sides = f1_score(y_test_seq, y_pred_binary_sides, average = 'weighted')

print(f"Accuracy = {accuracy_sides:.4f}, Precision = {precision_sides:.4f}, Recall = {recall_sides:.4f}, F1 Score = {f1_sides:.4f} -> sides")
print(classification_report(y_test_seq, y_pred_binary_sides))

#%% Predict the side labels

autolabels_left = model_left.predict(position_seq)
autolabels_right = model_right.predict(position_seq)

autolabels_sides = np.hstack((autolabels_left, autolabels_right))

autolabels_sides = np.vstack((np.zeros((before, 2)), autolabels_sides))

autolabels_sides_binary = (autolabels_sides > 0.5).astype(int)
# autolabels_sides_binary = smooth_column(np.array(autolabels_sides_binary))
autolabels_sides_binary = pd.DataFrame(autolabels_sides_binary, columns=["Left", "Right"])
autolabels_sides_binary.insert(0, "Frame", autolabels_sides_binary.index + 1)

autolabels_sides = pd.DataFrame(autolabels_sides, columns=["Left", "Right"])
autolabels_sides.insert(0, "Frame", autolabels_sides.index + 1)
"""