import re

# Fichier d'origine et fichier de sortie
input_path = r"C:\Users\user\Desktop\streamlit\data\dis3_cleaned.dat"
output_path = r"C:\Users\user\Desktop\streamlit\data\dis3_cleaned_resumed.dat"  # Tu peux remplacer ce nom si tu veux écraser l'ancien

# Variables à ne pas modifier
exclude_keys = {"id", "annee", "datetime", "mois", "trimestre"}

# Fonction de nettoyage des noms de variables
def resume_variable_name(var):
    var = re.sub(r'(levellagged|level|lagged|mom|constant|monthly)?$', '', var)  # supprime les suffixes
    var = re.sub(r'[^a-zA-Z0-9]', '', var)  # enlève caractères spéciaux
    return var.lower()

# Traitement ligne par ligne
with open(input_path, "r", encoding="utf-8") as infile, open(output_path, "w", encoding="utf-8") as outfile:
    for line in infile:
        new_pairs = []
        pairs = line.strip().split(',')
        for pair in pairs:
            if ':' in pair:
                key, value = pair.split(':', 1)
                key_clean = key.strip().lower()
                if key_clean in exclude_keys:
                    new_key = key  # On garde le nom original
                else:
                    new_key = resume_variable_name(key)
                new_pairs.append(f"{new_key}:{value}")
        outfile.write(','.join(new_pairs) + '\n')

print(f"✅ Fichier modifié enregistré sous : {output_path}")
