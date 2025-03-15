import os
import subprocess

# Chemin vers yt-dlp.exe (à adapter selon où tu l'as mis)
yt_dlp_path = r"P:\Dev\yt-dlp.exe"

# Liste des liens des playlists YouTube
playlists_urls = [
    "https://www.youtube.com/watch?v=Q-Pbh5eBYc8&list=PLcCRMUTnOp0XeOVzzSnmRvJs7znHng6jh"
]

# Dossier de téléchargement principal
download_folder = r"C:\Users\Farid\Downloads\YouTubePlaylists"

# Crée le dossier principal si nécessaire
os.makedirs(download_folder, exist_ok=True)

# Parcourir chaque playlist et la télécharger
for playlist_url in playlists_urls:
    try:
        print(f"Téléchargement de la playlist : {playlist_url}")
        
        # Commande yt-dlp pour télécharger en MP3
        command = [
            yt_dlp_path,
            "-x",  # Extraire uniquement l'audio
            "--audio-format", "mp3",  # Convertir au format MP3
            "--audio-quality", "0",  # Meilleure qualité audio possible
            "-o", os.path.join(download_folder, "%(playlist_title)s/%(title)s.%(ext)s"),  # Nom des fichiers
            playlist_url
        ]

        # Exécution de la commande
        subprocess.run(command, check=True)
        print(f"Playlist téléchargée avec succès : {playlist_url}")
    
    except subprocess.CalledProcessError as e:
        print(f"Une erreur est survenue pour la playlist : {playlist_url}\n{e}")

print("Téléchargements terminés pour toutes les playlists !")
