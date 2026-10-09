from pytubefix import YouTube
import os

yt = YouTube(str(input("Insert YouTube URL here: ")))

video = yt.streams.filter(only_audio=True).first()

print("Enter destination (leave blank for current destination): ")
destination = str(input(">> ")) or '.'

outputFile = video.download(output_path=destination)

base, ext = os.path.splitext(outputFile)
newFile = base + '.mp3'
os.rename(outputFile, newFile)

print(yt.title + " has been successfully downloaded!")