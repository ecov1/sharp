import os
import requests
from dotenv import load_dotenv


def main():
    load_dotenv()
    key = os.getenv('apiKey')
    host = 'https://api.the-odds-api.com'

    def getSports():
        sportsUrl = f"{host}/v4/sports/?apiKey={key}"
        response = requests.get(sportsUrl)

        if response.status_code == 200:
            data = response.json()  # Convert the raw text into a Python list/dict
            print("Successfully fetched data!")
        else:
            print(f"Error: {response.status_code}")
        
        print('Available Sports')
        #print(data)

        for entry in data:
            print([entry['group'], entry['title']])
    
    getSports()

    def get_pinnacle_odds():
        if not key:
            print("Error: API Key not found. Check your .env file.")
            return
        else:
            print('Key Exists')

    
        

if __name__ == "__main__":
    main()