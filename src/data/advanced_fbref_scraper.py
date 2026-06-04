import soccerdata as sd
import pandas as pd
import time

def scrape_advanced_tables(leagues: list, seasons: list) -> pd.DataFrame:
    """
    Expands the baseline 'summary' scraper to pull the deep tactical tables.
    
    WARNING: FBref rate limits heavily. This must be run with time.sleep()
    and ideally cached heavily.
    """
    
    print(f"Initializing soccerdata for advanced tables...")
    fb = sd.FBref(leagues=leagues, seasons=seasons)
    
    # We will fetch multiple stat_types and merge them on Match_ID and Player
    # Table types available in FBref Match Logs:
    stat_types = ['passing', 'passing_types', 'possession', 'defense', 'misc']
    
    merged_df = None
    
    for stat in stat_types:
        print(f"Fetching table: {stat}")
        try:
            df = fb.read_player_match_stats(stat_type=stat)
            
            # Flatten multi-index columns safely
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ['_'.join(col).strip() for col in df.columns.values]
                
            # Reset index to bring Player, Match, Date out of index
            df = df.reset_index()
            
            if merged_df is None:
                merged_df = df
            else:
                # Merge on the core composite key
                # Note: Exact column names depend on the flattened output, 
                # but generally ['league', 'season', 'game', 'team', 'player'] form the key.
                merge_keys = ['league', 'season', 'game', 'team', 'player']
                
                # Identify duplicate columns to avoid _x, _y suffixes
                cols_to_use = df.columns.difference(merged_df.columns).tolist() + merge_keys
                
                merged_df = merged_df.merge(df[cols_to_use], on=merge_keys, how='outer')
                
            # Respect rate limits
            time.sleep(3)
            
        except Exception as e:
            print(f"Error fetching {stat}: {e}")
            
    # Clean up column names for the prioritized features
    rename_map = {
        'Touches_Att Pen': 'touches_penalty_area',
        'Receiving_PrgR': 'progressive_passes_received',
        'Carries_PrgC': 'progressive_carries',
        'Passes_KP': 'key_passes',
        'Pass Types_Crs': 'crosses',
        'Pass Types_TB': 'through_balls'
    }
    
    # Safely rename if the columns exist
    merged_df = merged_df.rename(columns={k: v for k, v in rename_map.items() if k in merged_df.columns})
    
    return merged_df

if __name__ == "__main__":
    print("Advanced FBref Scraper Module Loaded.")
