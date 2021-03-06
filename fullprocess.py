"""
Author: Jahed Naghipoor
Date: December, 2021
This script is used for checking the drift and possible re-training of the model
Pylint score: 10/10
"""
import sys
import re
import os
import logging
import json

import pandas as pd
from sklearn.metrics import f1_score

import training
import ingestion
import scoring
import deployment
import diagnostics


logging.basicConfig(stream=sys.stdout, level=logging.INFO)

with open('./config.json', 'r') as file:
    config = json.load(file)

input_folder_path = config['input_folder_path']
dataset_path = config['output_folder_path']
prod_deployment_path = config['prod_deployment_path']
deployed_ingested_files = os.path.join(prod_deployment_path, "ingestedfiles.txt")
deployed_model= os.path.join(prod_deployment_path, "latestscore.txt")


def check_drift(dataframe):
    """
    check_drift function is used to check if the model is drifted or not

    Args:
        dataframe (pd.DataFrame): dataframe containing the data

    Returns:
        boolean: True if the model is drifted, False otherwise
    """
    # Check and read new data
    logging.info("Checking for new data")
    new_data = False

    # Step 1: Read ingestedfiles.txt from production deployment folder
    with open(deployed_ingested_files) as file:
        ingested_files = {line.strip('\n') for line in file.readlines()}
    

    # Step 2: Determine whether the source data folder has files that aren't
    # listed in ingestedfiles.txt
    source_files = set(os.listdir(input_folder_path))

    # If new data is not found, we can proceed. otherwise, we have to ingest new data
    if len(source_files.difference(ingested_files)) != 0:
        logging.info("No new data found")
        return False
    else:
        # Ingesting new data
        logging.info("Data found. Ingesting new data")
        ingestion.merge_multiple_dataframe()
    
        # Step 3: Checking for model drift
        logging.info("Checking for model drift")

        # Check whether the score from the deployed model is different from the
        # score from the model that uses the newest ingested data
        with open(deployed_model) as temp_file:
            deployed_score = re.findall(r'\d*\.?\d+', temp_file.read())[0]
            deployed_score = float(deployed_score)

        label = dataframe["exited"]
        features = dataframe.drop(["exited", "corporation"], axis=1)

        y_pred = diagnostics.model_predictions(features)
        new_score = f1_score(label.values, y_pred)

        # Deciding whether to proceed, part 2
        logging.info("Deployed score = %s", deployed_score)
        logging.info("New score = %s", new_score)

        # Check if model drifting happened
        if new_score < deployed_score:  # if new score is greater than deployed score
            logging.info("Drift occurred")
            return True
        else:
            logging.info("No drift")
            return False
        


def retrain(dataframe):
    """
    re-training and re-deploy the model
    """

    logging.info("Re-training model")
    training.train_model(dataframe)

    logging.info("Re-scoring model")
    scoring.score_model()

    logging.info("Re-deploying model")
    deployment.store_files()

    logging.info("Running diagnostics and reporting")
    os.system("python reporting.py")

    os.system("python apicalls.py")


if __name__ == '__main__':
    input_dataframe = pd.read_csv(
        os.path.join(
            dataset_path,
            'finaldata.csv'))

    DRIFT = check_drift(input_dataframe)
    if DRIFT is True:  # drift happened
        retrain(input_dataframe)
