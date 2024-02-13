"""
Created on Wed Oct 25 09:56:54 2023

@author: dhers

This code will prepare the .H5 files with the positions to be analyzed
"""

#%% Import libraries

import pandas as pd
import numpy as np
import os
import shutil

#%%

# At home:
path = r'C:\Users\dhers\Desktop\Videos_NOR'

# In the lab:
# path = r'/home/usuario/Desktop/Santi D/Videos_NOR' 

experiment = r'/2022-01_TORM_3h'

folder = path + experiment

# State video fps
fps = 25

# State the horizontal distance in cm between object 1 and object 2

dist = 14 # (cm), we will use it to scale the video coordinates

#%%

"""
This function turns _position.H5 files into _position.csv files
It also scales the coordenates to be expressed in cm (by using the distance between objects)
"""

def process_hdf5_file(path_name, distance, fps):
    
    # List all files in the folder
    h5_files = [file for file in os.listdir(path_name) if file.endswith('_position.h5')]
    
    for h5_file in h5_files:
        
        h5_file_path = os.path.join(path_name, h5_file)
        
        # Read the HDF5 file
        hdf_store = pd.read_hdf(h5_file_path)
        all_keys = hdf_store.keys()
        main_key = str(all_keys[0][0])
        position_df = pd.read_hdf(h5_file_path)[main_key]
    
        current_data = pd.DataFrame()
    
        max_i = 0 # To see when the mouse enters
    
        for key in position_df.columns:
            # We tap into the likelihood of each coordenate
            section, component = key[0], key[1]
            likelihood_key = (section, 'likelihood') 
            
            if component in ('x', 'y') and section not in ('obj_1','obj_2'):
                i = 0
                while i < len(position_df) and position_df[likelihood_key][i] < 0.9 :
                    # If the likelihood is less than 0.99 (mouse not in the video yet) the point is erased
                    position_df.loc[i, key] = np.nan
                    i += 1
                if max_i < i:
                    max_i = i
    
        for key in position_df.keys():
            if key[1] != "likelihood":
                # Replace the positions of the objects in every frame by their medians across the video
                if key[0] == "obj_1" or key[0] == "obj_2":
                    current_data[str(key[0]) + "_" + str(key[1])] = [position_df[key].median()] * len(position_df[key])
                else:
                    current_data[str( key[0] ) + "_" + str( key[1] )] = position_df[key]
            
        
        if "Hab" not in h5_file_path:
            
            # Calculate the medians
            obj_1_x = current_data['obj_1_x'].median()
            obj_2_x = current_data['obj_2_x'].median()
            
            """
            As the distance between objects is a constant that can be measured in real life,
            we can use it to scale different sized videos into the same size.
            """
            # Calculate the difference
            difference = obj_2_x - obj_1_x
            
            scale = (distance / difference) 
            
            # Apply the transformation to current_data
            current_data = current_data * scale
        
        else: # We ned to modify the script when there is no objects on the arena
            
            # Calculate the max and min point the nose can reach
            max_x = current_data['nose_x'].max()
            min_x = current_data['nose_x'].min()
            
            # Calculate the difference
            difference = max_x - min_x
            
            scale = (distance*2 / difference) + 0.008 # lets assume that the max width of the nose range is twice as the distance between objects
            
            # Apply the transformation to current_data
            current_data = current_data * scale
        
        # Determine the output file path in the same directory as the input file
        # Split the path and filename
        input_dir, input_filename = os.path.split(h5_file_path)
        
        # Remove the original extension
        filename_without_extension = os.path.splitext(input_filename)[0]
        
        # Add the new extension '.csv'
        output_csv_path = os.path.join(input_dir, filename_without_extension + '.csv')
    
        # Save the processed data as a CSV file
        current_data.to_csv(output_csv_path, index=False)
        
        # Calculate the moment when the mouse enters the video
        mouse_enters = max_i/fps
        
        #print(f"Processed {input_filename} and saved results to {output_csv_path}. The mouse took {mouse_enters} sec to enter the video and the scale is {scale*100}")
        
        print(f"{input_filename}. The mouse took {mouse_enters} sec. scale is {scale*100}.")

#%%

process_hdf5_file(folder, dist, fps)

#%%

"""
This code moves all files that have a word on its name to a subfolder.
"""

def filter_and_move_files(input_folder, word, folder_name):
    
    # Create a new subfolder
    output_folder = os.path.join(input_folder, folder_name, "position")
    os.makedirs(output_folder, exist_ok=True)

    # Get a list of all files in the input folder
    files = [f for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f))]

    # Iterate through files, move those without the word "position" to the "extra" subfolder
    for file in files:
        if word in file and ".csv" in file and "filtered" not in file:
            file_path = os.path.join(input_folder, file)
            output_path = os.path.join(output_folder, file)

            # Move the file to the "extra" subfolder
            shutil.move(file_path, output_path)

    print("Files filtered and moved successfully.")

#%%

"""
Finally we move all the files to their corresponding subfolder:
    - h5 files go away (we dont need them anymore)
    - I have habituation, trainings and testing so I create a folder for each
"""

groups  = ["Hab", "TR1", "TR2", "TS"]

for group in groups:
    filter_and_move_files(folder, group, group)

#%%

"""
Lets also clean all other files in the folder into a subfolder
"""

subfolder = os.path.join(folder, "extra")
os.makedirs(subfolder, exist_ok=True)
    
# Get a list of all files in the input folder
other_files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]

# Iterate through files, move those without the word "position" to the "extra" subfolder
for file in other_files:
    file_path = os.path.join(folder, file)
    output_path = os.path.join(subfolder, file)
    
    # Move the file to the "extra" subfolder
    shutil.move(file_path, output_path)