import os
import subprocess
import sys

def ffmpeg_est_installe():
    """
    Vérifie si FFmpeg est installé et accessible via le PATH.
    """
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def convertir_webm_en_mp3(input_file, output_file):
    """
    Convertit un fichier WebM en MP3 en utilisant FFmpeg.
    Si la conversion réussit, renvoie True. Sinon, renvoie False.
    """
    try:
        # Commande FFmpeg pour convertir WebM en MP3
        command = [
            "ffmpeg",
            "-i", input_file,    # Fichier source
            "-vn",               # Pas de vidéo
            "-ar", "44100",      # Fréquence d'échantillonnage
            "-ac", "2",          # Stéréo
            "-b:a", "320k",      # Qualité MP3
            "-y",                # Overwrite without asking
            output_file          # Fichier de sortie
        ]
        
        # Exécuter la commande FFmpeg
        print(f"🔄 Conversion de : {input_file}")
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"✅ Conversion réussie : {output_file}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors de la conversion de {input_file} : {e.stderr.decode().strip()}")
        return False
    except Exception as e:
        print(f"❌ Une erreur inattendue est survenue lors de la conversion de {input_file} : {e}")
        return False

def parcourir_et_convertir(dossier_racine):
    """
    Parcourt récursivement le dossier_racine et convertit tous les fichiers WebM en MP3.
    Supprime les fichiers WebM originaux après une conversion réussie.
    """
    for dossier, sous_dossiers, fichiers in os.walk(dossier_racine):
        for fichier in fichiers:
            if fichier.lower().endswith('.webm'):
                chemin_complet = os.path.join(dossier, fichier)
                nom_sans_ext = os.path.splitext(fichier)[0]
                chemin_mp3 = os.path.join(dossier, f"{nom_sans_ext}.mp3")
                
                # Vérifier si le fichier MP3 existe déjà pour éviter de le reconvertir
                if not os.path.exists(chemin_mp3):
                    conversion_reussie = convertir_webm_en_mp3(chemin_complet, chemin_mp3)
                    if conversion_reussie:
                        try:
                            os.remove(chemin_complet)
                            print(f"🗑️ Fichier original supprimé : {chemin_complet}")
                        except Exception as e:
                            print(f"❌ Impossible de supprimer {chemin_complet} : {e}")
                    else:
                        print(f"⚠️ Conversion échouée pour : {chemin_complet}. Le fichier WebM n'a pas été supprimé.")
                else:
                    print(f"ℹ️ Le fichier MP3 existe déjà : {chemin_mp3}. Suppression du WebM original.")
                    try:
                        os.remove(chemin_complet)
                        print(f"🗑️ Fichier original supprimé : {chemin_complet}")
                    except Exception as e:
                        print(f"❌ Impossible de supprimer {chemin_complet} : {e}")

def main():
    # Chemin racine de la clé USB
    cle_usb = r"D:/"
    
    # Vérifier si FFmpeg est installé
    if not ffmpeg_est_installe():
        print("❌ FFmpeg n'est pas installé ou n'est pas accessible via le PATH.")
        print("Veuillez installer FFmpeg et vous assurer qu'il est accessible depuis la ligne de commande.")
        sys.exit(1)
    
    # Vérifier si le chemin existe
    if not os.path.exists(cle_usb):
        print(f"❌ Le chemin spécifié n'existe pas : {cle_usb}")
        return
    
    # Lancer le processus de conversion
    parcourir_et_convertir(cle_usb)
    print("🎉 Conversion terminée pour tous les fichiers WebM.")

if __name__ == "__main__":
    main()
