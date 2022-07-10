# One Piece DVD ripper

This was an evening project to assist with backing up the absolutely ridiculous number of DVDs
that One Piece has (and it isn't even all episodes!) as we're tired of popping discs in and out
when binge watching them.

This code leaves a lot of be desired, and I have no idea how difficult it would be to get it to
work with other anime or shows. I created it because the Automatic-Ripping-Machine project
was unable to identify the One Piece discs and would only back them up, not create MKVs, and I was 
looking for a coding project.

There are still some hard coded values as well that are there because it can only be one thing
if you are ripping One Piece. Like the show ID for TVDB.

## How to use

Disclaimer, I have only tested this on Linux, YMMV.

The script is pretty easy to use, you need `MakeMKV` and `mkvmerge` in your path, and an API key
and pin for theTVDB. I'm too lazy to generate an install for this, so just use pipenv and run
the script from the shell.

Create a `.env` file with your keys:

```
API_KEY=YourKeyHere
API_PIN=YourPinHere
```

Run the script

```bash
pipenv shell
pipenv sync
./main.py /path/to/store/One/Piece first_episode_on_disc
```

Once finished you should have a new directory called `Season $number` which contains the episodes
in the format `One Piece - S$season_numberE$episode_number - $title.mkv`, e.g. 
`One Piece - S13E87- Hard Battles, One After Another! Devil's Fruit Eaters vs. Devil's Fruit Eaters!.mkv`
