import requests
from bs4 import BeautifulSoup
import csv

date = input("Please enter the date you want in the following format YYYY-MM-DD: ")
sanitized_date = date.replace("/", "-")  # Replace invalid characters

page = requests.get(f"https://www.yallakora.com/Match-Center/?date={date}")

def main(page):
    src = page.content
    soup = BeautifulSoup(src, 'lxml')
    
    # Find the match data (inspect the structure of the website to refine this selector)
    match_containers = soup.find_all('div', class_='matchCard')  # Adjust this based on actual structure
    
    matches = []
    
    for match in match_containers:
        # Extract match details like teams, score, time, etc.
        team_a = match.find('div', class_='teamA').text.strip() if match.find('div', class_='teamA') else 'N/A'
        team_b = match.find('div', class_='teamB').text.strip() if match.find('div', class_='teamB') else 'N/A'
        time = match.find('div', class_='matchTime').text.strip() if match.find('div', class_='matchTime') else 'N/A'
        result = match.find('div', class_='matchResult').text.strip() if match.find('div', class_='matchResult') else 'N/A'
        
        matches.append([team_a, team_b, time, result])
    
    # Write to a CSV file using the sanitized date
    with open(f'matches_{sanitized_date}.csv', mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Team A', 'Team B', 'Time', 'Result'])
        writer.writerows(matches)
    
    print(f"Data for {date} has been saved to matches_{sanitized_date}.csv")

main(page)
