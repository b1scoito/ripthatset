import argparse
import json
from time import sleep

import tidalapi


def enrich_with_tidal_links(input_data):
    """
    Adds TIDAL album links to each track in the input JSON data

    Parameters:
    input_data (dict): Dictionary containing track information

    Returns:
    dict: Input data enriched with TIDAL album links
    """
    # Initialize TIDAL session
    session = tidalapi.Session()
    session.login_oauth_simple()

    enriched_data = input_data.copy()
    total_tracks = len(enriched_data)

    print(f"Processing {total_tracks} tracks...")

    for i, (track_id, track_info) in enumerate(enriched_data.items(), 1):
        try:
            print(f"Processing track {i}/{total_tracks}: {track_info['title']}")

            # Search for the track
            results = session.search(f"{track_info['title']} {track_info['artist']}", limit=1)

            # Check if we have any track results
            if results['tracks'] and len(results['tracks']) > 0:
                found_track = results['tracks'][0]
                if hasattr(found_track, 'album') and found_track.album:
                    track_info['tidal_album_link_url'] = f"https://tidal.com/browse/album/{found_track.album.id}"
                    print(f"Found TIDAL album link for {track_info['title']}")
                else:
                    track_info['tidal_album_link_url'] = None
                    print(f"No album information found for {track_info['title']}")
            else:
                track_info['tidal_album_link_url'] = None
                print(f"No TIDAL match found for {track_info['title']}")

            # Add a small delay to avoid rate limiting
            sleep(1)

        except Exception as e:
            print(f"Error processing track {track_id}: {str(e)}")
            track_info['tidal_album_link_url'] = None

    return enriched_data

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Enrich JSON track data with TIDAL album links')
    parser.add_argument('input_file', help='Input JSON file path')
    parser.add_argument('output_file', help='Output JSON file path')

    args = parser.parse_args()

    try:
        # Read input file
        print(f"Reading input file: {args.input_file}")
        with open(args.input_file, 'r') as f:
            input_data = json.load(f)

        # Process the data
        enriched_data = enrich_with_tidal_links(input_data)

        # Save the results
        print(f"Saving results to: {args.output_file}")
        with open(args.output_file, 'w') as f:
            json.dump(enriched_data, f, indent=2)

        print("Processing completed successfully!")

    except FileNotFoundError:
        print(f"Error: Input file '{args.input_file}' not found")
        exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in input file '{args.input_file}'")
        exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
