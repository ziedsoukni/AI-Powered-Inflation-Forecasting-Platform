import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
import logging
import time
from datetime import datetime, timedelta
import schedule
import tabula
import PyPDF2
from hdfs import InsecureClient
import re
from tenacity import retry, stop_after_attempt, wait_fixed
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import warnings
import csv
import pdfplumber
from hdfs import HdfsError
import certifi

# Ignorer tous les avertissements de type 'Warning'
warnings.filterwarnings("ignore", message="No glyph for 9 in font")

# Define color codes

import os
from datetime import datetime

# Chemin du dossier et du fichier de log
LOG_DIR = r"C:\Users\user\Documents\datascript\log"
LOG_FILE = os.path.join(LOG_DIR, "pipeline.log")

# Vérifier si le dossier existe, sinon le créer
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Fonction de log
def log(message, level="INFO"):
    """
    Enregistre un message dans un fichier log et l'affiche avec des couleurs.

    Args:
        message (str): Message à enregistrer.
        level (str, optional): Niveau du log ("INFO", "WARNING", "ERROR", "DEBUG"). Par défaut : "INFO".
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{current_time}] [{level}] {message}"

    # Affichage coloré dans la console
    colors = {
        "INFO": f"{Colors.OKGREEN}{log_message}{Colors.ENDC}",
        "SUCCESS": f"{Colors.OKGREEN}{Colors.BOLD}{log_message}{Colors.ENDC}",  # Vert + Gras
        "WARNING": f"{Colors.WARNING}{log_message}{Colors.ENDC}",
        "ERROR": f"{Colors.FAIL}{log_message}{Colors.ENDC}",
        "DEBUG": f"{Colors.OKCYAN}{log_message}{Colors.ENDC}"
    }
    print(colors.get(level, log_message))

    # Écriture dans le fichier log
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(log_message + "\n")


# Fonction d'envoi d'email en cas d'erreur
def send_error_email(subject, body):
    try:
        sender_email = "zsoukni9@gmail.com"
        receiver_email = "ziedsou1@gmail.com"
        password = "zvyd qeut uxbx ehtj "  # Utiliser un mot de passe d'application sécurisé

        # Créer le message MIME
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = subject

        # Ajouter le contenu du message
        message.attach(MIMEText(body, "plain"))

        # Configurer le serveur SMTP de Gmail
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()  # Sécuriser la connexion
            server.login(sender_email, password)  # Connexion au serveur SMTP avec votre e-mail et mot de passe
            server.sendmail(sender_email, receiver_email, message.as_string())  # Envoi de l'email
            print(f"Erreur envoyée par mail : {subject}")
    except smtplib.SMTPException as e:
        print(f"Erreur SMTP lors de l'envoi de l'email : {e}")
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email : {e}")

# Exemple de fonction de scraping avec retry
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def scrape_table(url, filename, errors_list):
    try:
        log(f"Starting scraping for {filename}", "DEBUG")
        response = requests.get(url)
        response.raise_for_status()
        log(f"Connexion réussie pour {filename}!", "INFO")

        soup = BeautifulSoup(response.content, "html.parser")
        page_container = soup.find(class_="bct-page")
        if not page_container:
            error_message = f"Conteneur de page non trouvé pour {filename}"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs
            return

        # Extraire les en-têtes (Indicateurs)
        indicators = []
        header_table = page_container.find(class_="bct-header-fixed").find("table")
        if header_table:
            indicator_rows = header_table.find_all("tr")
            for row in indicator_rows:
                cols = row.find_all("td")
                indicators.append([td.text.strip() for td in cols])

        # Extraire les données
        rows = []
        content_table = page_container.find(class_="bct-table-fixed").find("table")
        if content_table:
            for row in content_table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) > 1:  # Ignorer les lignes vides ou non pertinentes
                    values = [col.text.strip() for col in cols]
                    rows.append(values)
            log(f"{len(rows)} lignes trouvées pour {filename}", "DEBUG")

        # Vérifier si des données ont été extraites
        if indicators and rows:
            indicators_row = indicators[0]
            df = pd.DataFrame(rows[1:], columns=indicators_row)

            output_path = os.path.join(r"C:\Users\user\Documents\data", filename)
            df.to_csv(output_path, index=False)
            log(f"Données sauvegardées dans '{output_path}'", "INFO")
        else:
            log(f"Impossible de trouver les données du tableau pour {filename}", "WARNING")
            errors_list.append(f"Erreur pour {filename}: Impossible de trouver les données du tableau.")  # Ajouter à la liste des erreurs

    except requests.RequestException as e:
        error_message = f"Erreur lors de la connexion pour {filename}: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs
    except Exception as e:
        error_message = f"Une erreur est survenue pour {filename}: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs

# Fonction pour exécuter les scrapers sur toutes les URLs et envoyer un seul email
def scrape_all_tables():
    errors_list = []  # Liste pour accumuler les erreurs

    url_taux_interet = "https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203260"
    url_pib = "https://www.bct.gov.tn/bct/siteprod/tableau_n.jsp?params=PL203150,PL203160"
    url_devise_annuelle = "https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL212010"
    url_tmm = "https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203105"

    # Exécution des scrapers
    scrape_table(url_taux_interet, "taux_interet.csv", errors_list)
    scrape_table(url_pib, "pib.csv", errors_list)
    scrape_table(url_devise_annuelle, "devise_annuelle.csv", errors_list)
    scrape_table(url_tmm, "tmm.csv", errors_list)

    # Si des erreurs ont été accumulées, envoie un seul email
    if errors_list:
        subject = "Erreurs survenues lors du scraping"
        body = "\n".join(errors_list)  # Accumuler toutes les erreurs dans le corps de l'email
        send_error_email(subject, body)

scrape_all_tables()






def extract_year(table):
    table_str = table.to_string()
    years = re.findall(r'\b20\d{2}\b', table_str)
    return years[0] if years else 'unknown_year'

# Spécifie le chemin du fichier PDF
pdf_file = r'C:\Users\user\Documents\data\2024_Situation_Mensuelle_BCT_fr.pdf'

# Dossiers où enregistrer les fichiers CSV
output_folder = r'C:\Users\user\Documents\data'
output_transformed_folder = r'C:\Users\user\Documents\datascript'

# Création des dossiers de sortie s'ils n'existent pas
os.makedirs(output_folder, exist_ok=True)
os.makedirs(output_transformed_folder, exist_ok=True)

# Extraire toutes les tables du PDF dans une liste de DataFrames
log(f"Lecture du fichier PDF : {pdf_file}", "INFO")
tables = tabula.read_pdf(pdf_file, pages='all', multiple_tables=True, lattice=True)

# Vérification si des tables ont été extraites
if not tables:
    log(f"Aucune table trouvée dans le PDF : {pdf_file}", "ERROR")
    exit()

# Filtrer et enregistrer les tables
for idx, table in enumerate(tables):
    try:
        log(f"Traitement de la table {idx + 1}", "INFO")

        # Vérifier que la table a suffisamment de lignes pour l'extraction
        if len(table) < 6:
            log(f"Table {idx + 1} ignorée (nombre insuffisant de lignes)", "WARNING")
            continue

        # Sélectionner les lignes 2, 4 et 6
        filtered_table = table.iloc[[1, 3, 5]]

        # Extraire l'année de la table
        year = extract_year(table)

        # Définir le nom du fichier CSV avec le chemin complet
        file_name = os.path.join(output_folder, f"pm_{year}.csv")

        # Enregistrer la table filtrée dans le fichier CSV
        filtered_table.to_csv(file_name, index=False)
        log(f"Table {idx + 1} enregistrée sous : {file_name}", "SUCCESS")

        # ---- NORMALISATION ET TRANSFORMATION ----

        # Charger le fichier CSV
        df = pd.read_csv(file_name)

        # Vérifier que le fichier n'est pas vide
        if df.empty:
            log(f"Le fichier {file_name} est vide après extraction.", "WARNING")
            continue

        # Vérifier si la colonne "Indicateurs" existe
        if "Indicateurs" not in df.columns:
            log(f"Colonne 'Indicateurs' absente dans {file_name}. Skipping...", "WARNING")
            continue

        # Conversion des valeurs en format numérique (suppression des espaces et conversion)
        df.iloc[:, 1:] = df.iloc[:, 1:].replace({' ': ''}, regex=True).apply(pd.to_numeric, errors='coerce')

        # Transformation du format large vers un format long
        df_long = df.melt(id_vars=["Indicateurs"], var_name="Date", value_name="Valeur")

        # Renommer les colonnes pour plus de clarté
        df_long.rename(columns={"Indicateurs": "Indicateur"}, inplace=True)

        # Définir le nom du fichier CSV transformé
        transformed_file_name = os.path.join(output_transformed_folder, f"pm_{year}_transforme.csv")

        # Enregistrement du fichier transformé
        df_long.to_csv(transformed_file_name, index=False)

        log(f"Fichier transformé et enregistré sous : {transformed_file_name}", "SUCCESS")

    except Exception as e:
        log(f"Erreur lors du traitement de la table {idx + 1} : {e}", "ERROR")




@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def scrape_table_ipc(url, filename, errors_list):
    try:
        log(f"Starting scraping for {filename}", "DEBUG")
        response = requests.get(url)
        response.raise_for_status()
        log("Connexion réussie!", "INFO")

        soup = BeautifulSoup(response.content, "html.parser")
        donnees_container = soup.find("div", class_="donnees")
        if not donnees_container:
            error_message = "Conteneur 'donnees' non trouvé"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour {filename}: {error_message}")
            return

        table = donnees_container.find("table", id="tblEmployee-0")
        if not table:
            error_message = "Tableau non trouvé"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour {filename}: {error_message}")
            return

        headers = []
        thead = table.find("thead", class_="thead-dark")
        if thead:
            header_row = thead.find("tr")
            if header_row:
                headers = [th.text.strip() for th in header_row.find_all("th")]
                if headers and headers[0] == "":
                    headers[0] = "Base"

        rows = []
        for row in table.find_all("tr"):
            cols = row.find_all(["th", "td"])
            if cols:
                row_data = [col.text.strip() for col in cols]
                if any(col.strip() for col in row_data):
                    rows.append(row_data)

        if rows:
            log(f"{len(rows)} lignes trouvées", "DEBUG")
        else:
            error_message = "Aucune ligne de données trouvée"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour {filename}: {error_message}")
            return

        if headers and rows:
            df = pd.DataFrame(rows, columns=headers)
        else:
            df = pd.DataFrame(rows)

        if df.iloc[0].isnull().all():
            df = df.iloc[1:].reset_index(drop=True)

        df = df.dropna(how="all")
        df = df.dropna(axis=1, how="all")
        df = df[
            ~df.iloc[:, 0].str.contains(
                "NoFilter|Unité|Source|Evolution de l'Indice des prix à la consommation familiale selon l'année de base - IPC",
                case=False,
                na=False,
            )
        ]

        # Supprimer la ligne contenant les mois spécifiques
        df = df[~df.apply(lambda x: x.astype(str).str.contains("juin 2024|juliet 2024|août 2024", case=False, na=False).any(), axis=1)]

        df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
        df = df.drop_duplicates()

        excel_path = rf"C:\Users\user\Documents\datascript\{filename}.csv"
        df.to_csv(excel_path, index=False)
        log(f"Données nettoyées et sauvegardées dans '{excel_path}'", "INFO")

    except requests.RequestException as e:
        error_message = f"Erreur lors de la connexion : {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")
    except Exception as e:
        error_message = f"Une erreur est survenue : {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")

# Fonction pour exécuter les scrapers et envoyer un seul email
def scrape_all_tables_ipc():
    errors_list = []  # Liste pour accumuler les erreurs

    url = "https://www.ins.tn/statistiques/90#"
    scrape_table_ipc(url, "inflation_resumes", errors_list)

    # Si des erreurs ont été accumulées, envoie un seul email
    if errors_list:
        subject = "Erreurs survenues lors du scraping IPC"
        body = "\n".join(errors_list)  # Accumuler toutes les erreurs dans le corps de l'email
        send_error_email(subject, body)

scrape_all_tables_ipc()



@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def scrape_exchange_rates(errors_list):
    try:
        log("Starting scraping for exchange rates", "DEBUG")
        url = "https://www.attijaribank.com.tn/fr/cours/cours-des-changes"
        response = requests.get(url, verify=False)

        response.raise_for_status()
        log("Connection successful for exchange rates!", "INFO")

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')
        
        if not table:
            error_message = "Exchange rates table not found"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour Taux de change: {error_message}")
            return

        # Extract table data
        rows = table.find_all('tr')
        data = []
        for row in rows:
            cols = row.find_all('td')
            cols = [col.text.strip() for col in cols]
            if len(cols) > 0:
                data.append(cols)

        if not data:
            error_message = "No exchange rate data found"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour Taux de change: {error_message}")
            return

        # Add timestamp to filename
        timestamp = datetime.now().strftime("%Y%m%d")
        output_path = rf'C:\Users\user\Documents\data\Taux_de_change{timestamp}.csv'

        # Create DataFrame and save to CSV
        df = pd.DataFrame(data, columns=["Monnaie", "Devise", "Unité", "Achat", "Vente"])
        df.to_csv(output_path, index=False)
        log(f"Exchange rates saved to '{output_path}'", "INFO")

        # Transformation et normalisation intégrées dans le processus
        normalized_output_path = rf'C:\Users\user\Documents\datascript\Taux_de_change{timestamp}_normalise.csv'
        with open(output_path, mode='r', encoding='utf-8') as infile, open(normalized_output_path, mode='w', encoding='utf-8', newline='') as outfile:
            reader = csv.DictReader(infile, delimiter=',')
            fieldnames = reader.fieldnames
            writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=',')
            writer.writeheader()
            
            for row in reader:
                # Transformation et normalisation dans une seule étape
                row['Achat'] = row['Achat'].replace(',', '.')
                row['Vente'] = row['Vente'].replace(',', '.')
                achat = float(row['Achat'])
                vente = float(row['Vente'])
                unite = int(row['Unité'])
                if unite != 1:
                    achat /= unite
                    vente /= unite
                    row['Unité'] = '1'
                row['Achat'] = str(achat)
                row['Vente'] = str(vente)
                writer.writerow(row)

        log(f"Normalized exchange rates saved to '{normalized_output_path}'", "INFO")

    except requests.RequestException as e:
        error_message = f"Error connecting to exchange rates page: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour Taux de change: {error_message}")
    except Exception as e:
        error_message = f"An error occurred while scraping exchange rates: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour Taux de change: {error_message}")

# Fonction pour exécuter le scraper et envoyer un seul email
def scrape_and_notify():
    errors_list = []  # Liste pour accumuler les erreurs

    scrape_exchange_rates(errors_list)

    # Si des erreurs ont été accumulées, envoie un seul email
    if errors_list:
        subject = "Erreurs survenues lors du scraping des taux de change"
        body = "\n".join(errors_list)  # Accumuler toutes les erreurs dans le corps de l'email
        send_error_email(subject, body)

# Exécute la fonction
scrape_and_notify()


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))

def fetch_and_save_inflation_data():
    url = "http://api.worldbank.org/v2/country/TN/indicator/FP.CPI.TOTL.ZG?format=json"
    errors_list = []  # Liste pour accumuler les erreurs

    try:
        log("Starting API request for inflation rates", "DEBUG")
        # Faire la requête GET à l'API
        response = requests.get(url)
        response.raise_for_status()  # Vérifier si la requête est réussie

        # Convertir la réponse JSON en un dictionnaire Python
        data = response.json()

        # Vérifier si des données existent dans la réponse
        if len(data) > 1 and isinstance(data[1], list):
            # Extraire toutes les années et les taux d'inflation
            records = [
                (entry["date"], round(float(entry["value"]), 2))  # Arrondir à 2 décimales
                for entry in data[1]
                if "value" in entry and entry["value"] is not None
            ]

            if records:
                # Créer un DataFrame avec les données de toutes les années
                df = pd.DataFrame(records, columns=["Année", "Taux d'inflation"])
                
                # Formater la colonne "Taux d'inflation" pour avoir 2 décimales
                df["Taux d'inflation"] = df["Taux d'inflation"].map(lambda x: f"{x:.2f}")

                # Enregistrer dans un fichier CSV
                file_path = r"C:\Users\user\Documents\datascript\Taux_inflation_tunisie.csv"
                df.to_csv(file_path, index=False, encoding="utf-8")

                log(f"Les taux d'inflation ont été enregistrés dans : {file_path}", "INFO")
            else:
                log("Aucune donnée d'inflation valide trouvée.", "WARNING")
                errors_list.append("Aucune donnée d'inflation valide trouvée.")
        else:
            log("Format de réponse inattendu ou aucune donnée disponible.", "WARNING")
            errors_list.append("Format de réponse inattendu ou aucune donnée disponible.")

    except requests.exceptions.RequestException as e:
        error_message = f"Erreur lors de la requête API : {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur API : {e}")
    except Exception as e:
        error_message = f"Une erreur est survenue : {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur : {e}")

    # Si des erreurs ont été accumulées, envoyer un email
    if errors_list:
        subject = "Erreurs survenues lors du fetch des taux d'inflation"
        body = "\n".join(errors_list)  # Accumuler toutes les erreurs dans le corps de l'email
        send_error_email(subject, body)

# Exécution de la fonction
fetch_and_save_inflation_data()








@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def scrape_table_balance(url, filename, errors_list):
    try:
        log(f"Starting scraping for {filename}", "DEBUG")
        response = requests.get(url)
        response.raise_for_status()
        log(f"Connexion réussie pour {filename}!", "INFO")

        soup = BeautifulSoup(response.content, "html.parser")
        page_container = soup.find(class_="bct-page")
        if not page_container:
            error_message = f"Conteneur de page non trouvé pour {filename}"
            log(error_message, "WARNING")
            errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs
            return

        # Extraire les en-têtes (Indicateurs)
        indicators = []
        header_table = page_container.find(class_="bct-header-fixed").find("table")
        if header_table:
            indicator_rows = header_table.find_all("tr")
            for row in indicator_rows:
                cols = row.find_all("td")
                indicators.append([td.text.strip() for td in cols])

        # Extraire les données
        rows = []
        content_table = page_container.find(class_="bct-table-fixed").find("table")
        if content_table:
            for row in content_table.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) > 1:  # Ignorer les lignes vides ou non pertinentes
                    values = [col.text.strip() for col in cols]
                    rows.append(values)
            log(f"{len(rows)} lignes trouvées pour {filename}", "DEBUG")

        # Vérifier si des données ont été extraites
        if indicators and rows:
            indicators_row = indicators[0]
            df = pd.DataFrame(rows[1:], columns=indicators_row)

            output_path = os.path.join(r"C:\Users\user\Documents\data", filename)
            df.to_csv(output_path, index=False)
            log(f"Données sauvegardées dans '{output_path}'", "INFO")
        else:
            log(f"Impossible de trouver les données du tableau pour {filename}", "WARNING")
            errors_list.append(f"Erreur pour {filename}: Impossible de trouver les données du tableau.")  # Ajouter à la liste des erreurs

    except requests.RequestException as e:
        error_message = f"Erreur lors de la connexion pour {filename}: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs
    except Exception as e:
        error_message = f"Une erreur est survenue pour {filename}: {e}"
        log(error_message, "ERROR")
        errors_list.append(f"Erreur pour {filename}: {error_message}")  # Ajouter à la liste des erreurs

# Fonction pour exécuter les scrapers sur toutes les URLs et envoyer un seul email
def scrape_all_tables_balance():
    errors_list = []  # Liste pour accumuler les erreurs

    # URLs des tableaux à scraper
    url_export = "https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203190"
    url_import = "https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203200"

    # Appels des fonctions de scraping
    scrape_table_balance(url_export, "export.csv", errors_list)
    scrape_table_balance(url_import, "import.csv", errors_list)

    # Si des erreurs ont été accumulées, envoie un seul email
    if errors_list:
        subject = "Erreurs survenues lors du scraping"
        body = "\n".join(errors_list)  # Accumuler toutes les erreurs dans le corps de l'email
        send_error_email(subject, body)

# Appel de la fonction pour scraper toutes les tables
scrape_all_tables_balance()


import os
import re
import pandas as pd
import pdfplumber
import traceback

def process_pdf(pdf_path, excel_output_path, output_dir):
    try:
        tables = []
        log("Ouverture du fichier PDF", "INFO")
        
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                extracted_table = page.extract_table()
                if extracted_table:
                    df = pd.DataFrame(extracted_table[1:], columns=extracted_table[0])
                    tables.append(df)
        
        if not tables:
            log("Aucune table n'a été extraite du PDF.", "WARNING")
            return
        
        log("Enregistrement des 3 premières lignes des tables dans un fichier Excel", "INFO")
        with pd.ExcelWriter(excel_output_path, engine='openpyxl') as writer:
            for idx, table in enumerate(tables):
                sheet_name = f"Table_{idx+1}"
                table.head(3).to_excel(writer, sheet_name=sheet_name, index=False)
        
        os.makedirs(output_dir, exist_ok=True)
        log(f"Les 3 premières lignes des tables ont été enregistrées dans '{excel_output_path}'", "INFO")
        
        xls = pd.ExcelFile(excel_output_path)
        all_transformed_data = []  # Liste pour collecter tous les DataFrames transformés
        
        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(excel_output_path, sheet_name=sheet_name)
                df.iloc[:, 1:] = df.iloc[:, 1:].replace({r'\s+': ''}, regex=True).apply(pd.to_numeric, errors='coerce')
                df_melted = df.melt(id_vars=[df.columns[0]], var_name="Date", value_name="Valeur")
                
                # Convertir la date en format "mois-année" et extraire l'année
                df_melted["Date"] = pd.to_datetime(df_melted["Date"], format='%Y-%m', errors='coerce')
                df_melted["Year"] = df_melted["Date"].dt.year  # Extraire l'année
                
                # Filtrer les données pour ne garder que les années >= 2005
                df_melted = df_melted[df_melted["Year"] >= 2005]
                
                # Formater la date en "mois-année"
                df_melted["Date"] = df_melted["Date"].dt.strftime('%m-%Y')
                
                year_match = re.search(r'\b(19|20)\d{2}\b', df.to_string())
                if year_match:
                    csv_filepath = os.path.join(output_dir, f"mm_{year_match.group()}_normalized.csv")
                    df_melted.to_csv(csv_filepath, index=False, encoding='utf-8')
                    log(f"Fichier normalisé sauvegardé: {csv_filepath}", "INFO")
                    
                    # Appliquer la transformation sur le fichier CSV normalisé
                    transformed_df = transform_csv(csv_filepath, output_dir)
                    if transformed_df is not None:
                        all_transformed_data.append(transformed_df)
                else:
                    log(f"Aucune année trouvée dans la feuille {sheet_name}", "WARNING")
            except Exception as e:
                log(f"Erreur lors du traitement de la feuille {sheet_name}: {e}", "ERROR")
        
        # Fusionner tous les DataFrames transformés en un seul DataFrame
        if all_transformed_data:
            final_df = pd.concat(all_transformed_data, ignore_index=True)
            final_csv_filepath = os.path.join(output_dir, "all_transformed_data.csv")
            final_df.to_csv(final_csv_filepath, index=False)
            log(f"Toutes les données transformées ont été enregistrées dans '{final_csv_filepath}'", "INFO")
        
    except Exception as e:
        log(f"Erreur lors du traitement du fichier PDF: {e}", "ERROR")
        traceback.print_exc()

def transform_csv(csv_filepath, output_dir):
    try:
        # Lire le fichier CSV normalisé
        df = pd.read_csv(csv_filepath)
        
        # Séparer les données en fonction des indicateurs (M1, M2, M3)
        m1_df = df[df['Indicateurs(cid:9)'] == 'MASSE MONETAIRE M1'][['Date', 'Valeur']].rename(columns={'Valeur': 'M1'})
        m2_df = df[df['Indicateurs(cid:9)'] == 'MASSE MONETAIRE M2'][['Date', 'Valeur']].rename(columns={'Valeur': 'M2'})
        m3_df = df[df['Indicateurs(cid:9)'] == 'MASSE MONETAIRE M3'][['Date', 'Valeur']].rename(columns={'Valeur': 'M3'})
        
        # Fusionner les DataFrames sur la colonne 'Date'
        merged_df = pd.merge(m1_df, m2_df, on='Date', how='outer')
        merged_df = pd.merge(merged_df, m3_df, on='Date', how='outer')
        
        # Remplacer les valeurs manquantes par 0 avant de convertir en entiers
        merged_df['M1'] = merged_df['M1'].fillna(0).astype(int)
        merged_df['M2'] = merged_df['M2'].fillna(0).astype(int)
        merged_df['M3'] = merged_df['M3'].fillna(0).astype(int)
        
        # Réorganiser les colonnes
        merged_df = merged_df[['M1', 'M2', 'M3', 'Date']]
        
        return merged_df  # Retourner le DataFrame transformé
        
    except Exception as e:
        log(f"Erreur lors de la transformation du fichier CSV: {e}", "ERROR")
        return None

if __name__ == "__main__":
    process_pdf(
        pdf_path="C:/Users/user/Documents/data/2024_Agregats_monnaie_contreparties_fr.pdf",
        excel_output_path="C:/Users/user/Documents/data/extracted_first_3_rows_tables.xlsx",
        output_dir="C:/Users/user/Documents/datascript"
    )

    
def transformation_globale(files_mapping):
    mois_map = {
    "Janvier": "01", "Février": "02", "Mars": "03", "Avril": "04", "Mai": "05", "Juin": "06",
    "Juillet": "07", "Août": "08", "Septembre": "09", "Octobre": "10", "Novembre": "11", "Décembre": "12"
}
    def transformation(file_path, output_path):
        """Transformation des fichiers avec indicateurs et mois"""
        try:
            log(f"Transformation du fichier {file_path}", "INFO")
            df = pd.read_csv(file_path)
            df.iloc[:, 1:] = df.iloc[:, 1:].replace(",", ".", regex=True).apply(pd.to_numeric, errors='coerce')
            df_long = df.melt(id_vars=["Indicateurs"], var_name="Année", value_name="Valeur")
            df_long.rename(columns={"Indicateurs": "Mois"}, inplace=True)
            df_long["Date"] = df_long["Année"] + "-" + df_long["Mois"].map(mois_map)
            df_final = df_long[["Date", "Valeur"]].copy()
            df_final.sort_values(by="Date", inplace=True)
            df_final.to_csv(output_path, index=False, sep=";", encoding="utf-8")
            log(f"Fichier enregistré : {output_path}", "SUCCESS")
        except Exception as e:
            error_msg = f"Erreur transformation {file_path}: {e}"
            log(error_msg, "ERROR")
            send_error_email("Erreur de transformation", error_msg)

    def normaliser_csv(fichier_entree, fichier_sortie):
        """Normalisation des devises"""
        try:
            log(f"Normalisation de {fichier_entree}", "INFO")
            if not os.path.exists(fichier_entree):
                raise FileNotFoundError(f"Introuvable : {fichier_entree}")
            df = pd.read_csv(fichier_entree)
            df.columns = ['devise'] + [str(year) for year in range(2019, 2025)]
            df.replace(',', '.', regex=True, inplace=True)
            for year in range(2019, 2025):
                df[str(year)] = pd.to_numeric(df[str(year)], errors='coerce')
            df_long = df.melt(id_vars=['devise'], var_name='année', value_name='taux')
            df_long['devise'] = df_long['devise'].str.lower().str.normalize('NFKD').str.encode('ascii', errors='ignore').str.decode('utf-8')
            df_long.to_csv(fichier_sortie, index=False, sep=';', encoding='utf-8')
            log(f"Fichier normalisé : {fichier_sortie}", "SUCCESS")
        except Exception as e:
            error_msg = f"Erreur normalisation {fichier_entree}: {e}"
            log(error_msg, "ERROR")
            send_error_email("Erreur de normalisation", error_msg)

    def process_csv(file_path, output_path):
        """Traitement des fichiers d'import/export"""
        try:
            log(f"Traitement de {file_path}", "INFO")
            df = pd.read_csv(file_path, dtype=str)
            df = df[~df.iloc[:, 0].str.contains("En quantités", na=False)]
            df = df.melt(id_vars=[df.columns[0]], var_name="Année", value_name="Valeurs")
            df = df.drop(columns=[df.columns[0]])
            df["Valeurs"] = df["Valeurs"].str.replace(',', '.', regex=True)
            df.to_csv(output_path, index=False, sep=";", encoding="utf-8")
            log(f"Fichier traité : {output_path}", "SUCCESS")
        except Exception as e:
            error_msg = f"Erreur traitement {file_path}: {e}"
            log(error_msg, "ERROR")
            send_error_email("Erreur de traitement", error_msg)

    def transform_pib_data(input_path, output_path):
        """Transformation spécifique pour PIB"""
        try:
            log(f"Transformation PIB {input_path}", "INFO")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            df = pd.read_csv(input_path)
            df_prices = df[df["Indicateurs"] == "Prix courants"].copy()
            df_prices.drop(columns=["Indicateurs"], inplace=True)
            df_prices = df_prices.applymap(lambda x: float(str(x).replace(',', '.')))
            df_long = df_prices.melt(var_name="Année", value_name="Prix courants")
            df_long["Année"] = df_long["Année"].astype(int)
            df_long.to_csv(output_path, index=False, sep=',', encoding='utf-8')
            log(f"Fichier PIB transformé : {output_path}", "SUCCESS")
        except Exception as e:
            error_msg = f"Erreur transformation PIB {input_path}: {e}"
            log(error_msg, "ERROR")
            send_error_email("Erreur de transformation PIB", error_msg)

    # Exécution des transformations en fonction du fichier
    for file_path, output_path in files_mapping.items():
        if os.path.exists(file_path):
            if "tmm" in file_path or "taux_interet" in file_path:
                transformation(file_path, output_path)
            elif "devise_annuelle" in file_path:
                normaliser_csv(file_path, output_path)
            elif "export" in file_path or "import" in file_path:
                process_csv(file_path, output_path)
            elif "pib" in file_path:
                transform_pib_data(file_path, output_path)
        else:
            error_msg = f"Fichier introuvable : {file_path}"
            log(error_msg, "WARNING")
            send_error_email("Fichier introuvable", error_msg)

# Exécution de la fonction globale
files_mapping = {
    r"C:\Users\user\Documents\data\tmm.csv": r"C:\Users\user\Documents\datascript\tmm_normalise.csv",
    r"C:\Users\user\Documents\data\taux_interet.csv": r"C:\Users\user\Documents\datascript\taux_interet_normalise.csv",
    r"C:\Users\user\Documents\data\devise_annuelle.csv": r"C:\Users\user\Documents\datascript\devise_annuelle_transformee.csv",
    r"C:\Users\user\Documents\data\export.csv": r"C:\Users\user\Documents\datascript\export_modified.csv",
    r"C:\Users\user\Documents\data\import.csv": r"C:\Users\user\Documents\datascript\import_modified.csv",
    r"C:\Users\user\Documents\data\pib.csv": r"C:\Users\user\Documents\datascript\pib_transforme.csv"
}

transformation_globale(files_mapping)





def upload_csv_to_hdfs(local_directory, hdfs_directory, hdfs_url='http://localhost:9870'):
    client = InsecureClient(hdfs_url)

    # Vérifier si le répertoire local existe
    if not os.path.exists(local_directory):
        log(f"Le répertoire local '{local_directory}' n'existe pas.", level="ERROR")
        send_error_email("Erreur : Répertoire local introuvable", f"Le répertoire local '{local_directory}' n'existe pas.")
        return

    # Lister tous les fichiers CSV dans le répertoire local
    csv_files = [f for f in os.listdir(local_directory) if f.endswith('.csv')]

    if not csv_files:
        log("Aucun fichier CSV trouvé dans le répertoire local.", level="WARNING")
        return

    # Vérifier si le répertoire HDFS existe, sinon le créer
    try:
        if not client.status(hdfs_directory, strict=False):
            log(f"Le répertoire HDFS '{hdfs_directory}' n'existe pas, création...", level="INFO")
            client.makedirs(hdfs_directory)
            log(f"Répertoire HDFS '{hdfs_directory}' créé avec succès.", level="INFO")
    except HdfsError as e:
        log(f"Erreur lors de la vérification de l'existence du répertoire HDFS : {e}", level="ERROR")
        send_error_email("Erreur : Problème avec le répertoire HDFS", f"Erreur lors de la vérification de l'existence du répertoire HDFS : {e}")
        return

    # Télécharger chaque fichier CSV dans HDFS
    for file_name in csv_files:
        local_csv_path = os.path.join(local_directory, file_name)
        hdfs_path = os.path.join(hdfs_directory, file_name)

        try:
            # Vérifier si le fichier existe déjà dans HDFS
            if client.status(hdfs_path, strict=False):
                client.delete(hdfs_path)
                log(f"{Colors.OKBLUE}Le fichier {file_name} existait déjà dans HDFS, il a été supprimé.{Colors.ENDC}", level="INFO")

            # Copier le fichier CSV dans HDFS
            client.upload(hdfs_path, local_csv_path)
            log(f"{Colors.OKGREEN}Fichier {file_name} téléchargé avec succès vers {hdfs_path}.{Colors.ENDC}", level="INFO")

        except HdfsError as e:
            log(f"Erreur lors du téléchargement du fichier {file_name} : {e}", level="ERROR")
            send_error_email(f"Erreur lors du téléchargement du fichier {file_name}", f"Erreur lors du téléchargement du fichier {file_name} : {e}")

# Exemple d'appel de la fonction
upload_csv_to_hdfs(r'C:\Users\user\Documents\datascript', '/datalake/raw_data/')




# Fonction pour vérifier si c'est le premier jour du mois
def is_first_day_of_month():
    return datetime.now().day == 1

# Fonction pour vérifier si c'est le premier jour de l'année
def is_first_day_of_year():
    return datetime.now().month == 1 and datetime.now().day == 1

# Planifier les tâches
def schedule_tasks():
    # Tâches quotidiennes
    schedule.every().day.at("02:07").do(scrape_and_notify)  # Quotidien à minuit
    schedule.every().day.at("02:07").do(upload_csv_to_hdfs)  # Quotidien à minuit
    # Tâches mensuelles (le premier jour du mois)
    schedule.every().day.at("02:07").do(lambda: scrape_all_tables() if is_first_day_of_month() else None)
    schedule.every().day.at("02:07").do(lambda: scrape_all_tables_ipc(url="https://www.ins.tn/statistiques/90#", filename="inflation_resumes") if is_first_day_of_month() else None)
    schedule.every().day.at("02:07").do(lambda: upload_csv_to_hdfs(local_directory=r'C:\Users\user\Documents\datascript', hdfs_directory='/datalake/raw_data/') if is_first_day_of_month() else None)
    # Tâches annuelles (le premier jour de l'année)
    schedule.every().day.at("02:07").do(lambda: scrape_table_balance(url="https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203190", filename="export.csv") if is_first_day_of_year() else None)
    schedule.every().day.at("02:07").do(lambda: scrape_table_balance(url="https://www.bct.gov.tn/bct/siteprod/tableau_statistique_a.jsp?params=PL203200", filename="import.csv") if is_first_day_of_year() else None)

    schedule.every().day.at("02:07").do(lambda: fetch_and_save_inflation_data() if is_first_day_of_year() else None)
    schedule.every().day.at("02:07").do(lambda: transformation_globale(files_mapping) if is_first_day_of_year() else None)
    schedule.every().day.at("02:07").do(lambda: upload_csv_to_hdfs(local_directory=r'C:\Users\user\Documents\datascript', hdfs_directory='/datalake/raw_data/') if  is_first_day_of_year() else None)

# Planifier les tâches au démarrage
schedule_tasks()

# Boucle pour exécuter les tâches planifiées
while True:
    schedule.run_pending()
    time.sleep(1)
