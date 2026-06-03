import soccerdata as sd

# Initialize FBref scraper
fbref = sd.FBref(leagues=['ENG-Premier League', 'ESP-La Liga', 
                           'GER-Bundesliga', 'ITA-Serie A', 'FRA-Ligue 1'],
                 seasons=['2425', '2526'])

# Scrape passing table
passing_df = fbref.read_player_season_stats(stat_type='passing')

# Save
passing_df.to_csv('C:/Users/Elie/data/csv/player_passing_stats.csv', index=True)
print(f"Passing stats scraped: {passing_df.shape}")
