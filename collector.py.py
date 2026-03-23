import requests
import pandas as pd
from datetime import datetime

def get_ecb_rate():
    url = "https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.MRR_FR.LEV?format=jsondata&lastNObservations=1"
    response = requests.get(url)
    data = response.json()
    rate = data["dataSets"][0]["series"]["0:0:0:0:0:0"]["observations"]["0"][0]
    return rate

print("EZB Zinssatz:", get_ecb_rate(), "%")