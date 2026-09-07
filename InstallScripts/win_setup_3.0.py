# pip install customtkinter

import os
import sys
import json
import secrets
import string
import urllib.request
import certifi
import ssl
import zipfile
import tarfile
import subprocess
import time
import webbrowser
import logging
import threading
import pymsi
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

# --- Configuration ---
PYTHON_MIN_VERSION = (3, 8)
PYTHON_MAX_VERSION = (3, 11)
DB_PORT = 3306
DELETE_DOWNLOADS = False

MYSQL_URL = "https://dev.mysql.com/get/Downloads/MySQL-5.0/mysql-5.7.41-winx64.zip"
NODE_URL = "https://nodejs.org/dist/v18.20.4/node-v18.20.4-win-x64.zip"
PYTHON_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
MZMINE_URL = "https://github.com/mzmine/mzmine2/releases/download/v2.53/MZmine-2.53-Windows.zip"
MORPHEUS_URL = "https://github.com/cwenger/Morpheus/releases/download/r287/Morpheus_mzML.zip"
MSBOOSTER_URL = "https://github.com/Nesvilab/MSBooster/releases/download/v1.3.31/MSBooster-1.3.31.jar"
PERCOLATOR_URL = "https://github.com/percolator/percolator/releases/download/rel-3-09/percolator.exe"
PHILOSOPHER_URL = "https://github.com/Nesvilab/philosopher/releases/download/v5.1.0/philosopher_v5.1.0_windows_amd64.zip"

# --- Thread-Safe GUI Logging Handler ---
class GUIHandler(logging.Handler):
    def __init__(self, textbox):
        super().__init__()
        self.textbox = textbox

    def emit(self, record):
        msg = self.format(record)
        # Use .after() to safely update the GUI from the worker thread
        self.textbox.after(0, self.append_text, msg)

    def append_text(self, msg):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", msg + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

# --- Setup Functions (Modified for GUI) ---
def download_file(url: str, dest_path: Path, logger, progress_bar):

    # 1. Create a secure SSL context using certifi's CA bundle
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    
    # 2. Configure headers (GitHub requires a User-Agent to avoid 403 blocks)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python-urllib/3.x'
    }
    
    # 3. Create the request object
    req = urllib.request.Request(url, headers=headers)
    
    logger.info(f"Downloading {url}...")
    
    # 4. Open the URL with the custom SSL context
    progress_bar.set(0.0)
    with urllib.request.urlopen(req, context=ssl_context) as response:

        # progress tracking
        total_size = int(response.headers.get('Content-Length', 0))
        downloaded_size = 0

        # Open local file in Write-Binary ('wb') mode
        with open(dest_path, 'wb') as local_file:
            # Read and write in 16KB chunks to keep memory footprint low
            while chunk := response.read(16384):
                local_file.write(chunk)
                downloaded_size += len(chunk)
                        
                if total_size > 0:
                    progress_ratio = downloaded_size / total_size
                    pct = int(progress_ratio * 100)
                    # Update UI bar 
                    progress_bar.set(progress_ratio)

    progress_bar.set(1.0)
    return dest_path

def extract_archive(archive_path: Path, dest_dir: Path, logger):
    logger.info(f"Extracting {archive_path.name}...")
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
    elif archive_path.name.endswith(".tar.bz2") or archive_path.name.endswith(".tar"):
        with tarfile.open(archive_path, "r:*") as tar_ref:
            tar_ref.extractall(dest_dir)
    
    if DELETE_DOWNLOADS:
        archive_path.unlink()
        logger.debug(f"Deleted archive: {archive_path.name}")

def extract_msi(msi_path: Path, software_dir: Path, logger):
    logger.info(f"Extracting {msi_path}...")

    msi_path = os.path.normpath(os.path.abspath(msi_path))
    software_dir = os.path.normpath(os.path.abspath(software_dir))

    cmd = [
        "msiexec.exe", 
        "/i", f'"{msi_path}"', 
        "/qn", 
        f'TARGETDIR="{software_dir}"',
        "MSIINSTALLPERUSER=1",
        "ALLUSERS=2"
    ]
    
    try:
        # Execute the command and block until it finishes
        result = subprocess.run(cmd, check=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info("Extraction completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.info(f"Error extracting MSI: {e}")
        return False

def run_cmd(args, cwd=None, check=True, capture=False, new_console=False, logger=None):
    kwargs = {'cwd': cwd, 'check': check}
    if capture:
        kwargs.update({'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'text': True})
    if new_console and sys.platform == "win32":
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
        
    if logger:
        logger.debug(f"Running command: {' '.join(str(a) for a in args)}")
    return subprocess.run(args, **kwargs)

def setup_mysql(base_dir: Path, software_dir: Path, logger, app, progress_bar):
    logger.info("\n===== Configuring MySQL Community Server =====")
    mysql_dir = software_dir / "mysql-5.7.41-winx64"
    mysql_bin = mysql_dir / "bin"
    
    if not mysql_dir.exists():
        zip_path = software_dir / "mysql-5.7.41-winx64.zip"
        download_file(MYSQL_URL, zip_path, logger, progress_bar)
        extract_archive(zip_path, software_dir, logger)

    data_dir = base_dir / "data"
    my_cnf = mysql_dir / "my.cnf"

    if not data_dir.exists():
        logger.info("Creating data directory and configuration...")
        data_dir.mkdir(parents=True)
        my_cnf.write_text(f"[mysqld]\nbasedir=\"{mysql_dir.as_posix()}\"\ndatadir=\"{data_dir.as_posix()}\"\nport={DB_PORT}\nexplicit-defaults-for-timestamp=ON\nlog-syslog=OFF\ntls_version=TLSv1.2\n\n[client]\nport={DB_PORT}\n")

        db_config = {"Database Port": DB_PORT, "Database Name": "maspeqc", "User": "maspeqc"}
        for target in [base_dir / "mpmf-pipeline" / "Config" / "database-login.json", base_dir / "mpmf-server" / "database-login.json"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, 'w') as f:
                json.dump(db_config, f)

        logger.info("Initializing MySQL server...")
        run_cmd([mysql_bin / "mysqld.exe", "--initialize-insecure", "--console"], logger=logger)

    logger.info("Starting MySQL server in a new window...")
    subprocess.Popen([mysql_bin / "mysqld.exe", "--console"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    logger.info("Waiting for MySQL server to become ready...")
    for _ in range(30):
        result = run_cmd([mysql_bin / "mysqladmin.exe", "-s", "ping"], check=False, capture=True)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("MySQL server failed to start or respond to ping.")

    result = run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "SHOW DATABASES LIKE 'maspeqc';"], capture=True)
    if "maspeqc" not in result.stdout:
        logger.info("Creating database 'maspeqc'...")
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "CREATE DATABASE maspeqc;"], logger=logger)

        chars = string.ascii_letters + string.digits
        password = "".join(secrets.choice(chars) for _ in range(16))
        
        (base_dir / "mpmf-pipeline" / "Config" / ".maspeqc_gen").write_text(password)
        (base_dir / "mpmf-server" / ".maspeqc_gen").write_text(password)

        logger.info("Creating user and setting privileges...")
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", f"CREATE USER 'maspeqc'@'localhost' IDENTIFIED BY '{password}';"])
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "GRANT ALL PRIVILEGES ON `maspeqc`.* TO `maspeqc`@`localhost`; FLUSH PRIVILEGES;"])
        
        # Request MySQL root password via GUI dialog
        def ask_password():
            dialog = ctk.CTkInputDialog(text="Enter a new database password for the 'root' user:", title="MySQL Root Password")
            return dialog.get_input()
        
        # Must call dialog from main thread, wait for result
        root_pass = app.wait_for_gui_input(ask_password)
        if root_pass:
            run_cmd([mysql_bin / "mysqladmin.exe", "-u", "root", "password", root_pass])
            logger.info("Root password set successfully.")
        else:
            logger.warning("No root password provided.")

def setup_nodejs(base_dir: Path, software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring Node.js =====")
    node_dir = software_dir / "node-v18.20.4-win-x64"
    if not node_dir.exists():
        zip_path = software_dir / "node-v18.20.4-win-x64.zip"
        download_file(NODE_URL, zip_path, logger, progress_bar)
        extract_archive(zip_path, software_dir, logger)

    server_dir = base_dir / "mpmf-server"
    if server_dir.exists() and not (server_dir / "node_modules").exists():
        logger.info("Installing Node modules...")
        env = os.environ.copy()
        env["PATH"] = f"{node_dir};{env['PATH']}"
        run_cmd([node_dir / "npm.cmd", "install"], cwd=server_dir, logger=logger)
        
        logger.info("Starting Node.js configuration server...")
        subprocess.Popen(f'"{node_dir / "npm.cmd"}" start --setup', cwd=server_dir, env=env, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        time.sleep(3) 
        webbrowser.open("http://localhost/configuration")
        messagebox.showinfo("Action Required", "Press OK once you have completed the browser configuration.")
        logger.info("Browser configuration completed.")

def setup_local_python(software_dir: Path, logger, progress_bar) -> Path:
    logger.info("\n===== Configuring Local Python =====")
    python_dir = software_dir / "Python"
    python_exe = python_dir / "python.exe"

    if python_exe.exists():
        logger.info(f"Found local Python installation at {python_dir}")
        return python_exe

    logger.info("Could not find local Python installation. Downloading Python 3.10.11...")
    installer_path = software_dir / "python-3.10.11-amd64.exe"
    download_file(PYTHON_URL, installer_path, logger, progress_bar)

    logger.info("\nStarting a minimal Python installation.")

    # Using str(python_dir.resolve()) ensures native Windows backslashes for the installer argument
    target_dir = str(python_dir.resolve())
    
    install_cmd = [
        str(installer_path),
        #"/quiet",  # <-- This flag suppresses the GUI
        "InstallAllUsers=0",
        "Shortcuts=0",
        "Include_doc=0",
        "Include_launcher=0",
        "Include_tcltk=0",
        "Include_test=0",
        f"TargetDir={target_dir}"
    ]
    
    run_cmd(install_cmd)
    
    if DELETE_DOWNLOADS and installer_path.exists():
        installer_path.unlink()
        
    return python_exe

def setup_python_env(base_dir: Path, local_python_exe: Path, logger):
    logger.info("\n===== Configuring Python Environment =====")
    pipeline_dir = base_dir / "mpmf-pipeline"
    venv_dir = pipeline_dir / ".venv"
    
    # Fallback to the system executable if the local install failed/was skipped
    python_alias = local_python_exe if local_python_exe.exists() else sys.executable
    
    if pipeline_dir.exists() and not venv_dir.exists():
        logger.info(f"Creating virtual environment using {python_alias}...")
        run_cmd([str(python_alias), "-m", "venv", ".venv"], cwd=pipeline_dir)
        
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        
        logger.info("Installing Python requirements...")
        run_cmd([str(pip_exe), "install", "-r", "requirements.txt"], cwd=pipeline_dir)
        
        if (pipeline_dir / "Config" / ".maspeqc_gen").exists():
            logger.info("Running MPMF_Database_SetUp.py...")
            run_cmd([str(python_exe), "MPMF_Database_SetUp.py"], cwd=pipeline_dir)

def setup_mzmine(software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring MZmine =====")
    mzmine_dir = software_dir / "MZmine-2.53-Windows"
    if not mzmine_dir.exists():
        zip_path = software_dir / "MZmine-2.53-Windows.zip"
        download_file(MZMINE_URL, zip_path, logger, progress_bar)
        extract_archive(zip_path, software_dir, logger)
        
    logger.info("Testing MZmine launch (Please close MZmine once it opens)...")
    run_cmd([mzmine_dir / "bin" / "java.exe", "-classpath", "lib\\*", "io.github.mzmine.main.MZmineCore"], cwd=mzmine_dir, logger=logger)

def setup_morpheus(software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring Morpheus =====")
    morpheus_dir = software_dir / "Morpheus (mzML)"
    if not morpheus_dir.exists():
        zip_path = software_dir / "Morpheus_mzML.zip"
        download_file(MORPHEUS_URL, zip_path, logger, progress_bar)
        extract_archive(zip_path, software_dir, logger)

def setup_proteowizard(software_dir: Path, logger):
    logger.info("\n===== Configuring ProteoWizard (msconvert) =====")
    pwiz_dir = software_dir / "ProteoWizard"
    
    if not pwiz_dir.exists():
        tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
        if not tar_files:
            logger.warning("ProteoWizard requires manual download due to licensing.")
            webbrowser.open("https://proteowizard.sourceforge.io/download.html")
            messagebox.showinfo("Action Required", f"Please download the 'Windows 64-bit tar.bz2' to {software_dir}\n\nPress OK when the download is complete.")
            logger.info("Manual download confirmed.")
            tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
            
        if tar_files:
            pwiz_dir.mkdir(exist_ok=True)
            extract_archive(tar_files[0], pwiz_dir, logger)
            logger.info("Extracted ProteoWizard.")
        else:
            raise FileNotFoundError("ProteoWizard archive not found.")

def setup_diann(software_dir: Path, logger):
    logger.info("\n===== Configuring DIA-NN (for MSBooster) =====")
    diann_dir = software_dir / "DIA-NN"
    
    if not diann_dir.exists():
        logger.warning("DIA-NN requires manual download due to licensing.")
        logger.warning("DIA-NN is for academic use only. Please read the license carefully. \nIf you do not meet the requirements for academic use, please do not download.")

        response = messagebox.askyesno("DIA-NN Academic Confirmation", "Are you using MaSpeQC for academic or research purposes?")

        if response:
            webbrowser.open("https://github.com/vdemichev/DiaNN/releases")
            messagebox.showinfo("Action Required", f"Please download the 'DIA-NN-Academia-2.2.0.msi' to {software_dir}\n\nPress OK when the download is complete.")
            logger.info("Manual download confirmed.")

            logger.info("Extracting DIA-NN MSI...")
            result = extract_msi(software_dir / "DIA-NN-Academia-2.2.0.msi", software_dir, logger)
            return result
        else:
            logger.warning("Proteomics QC will not use MSBooster for MS-MS metrics.")
            return False
            
        
def setup_msfragger(software_dir: Path, logger):
    logger.info("\n===== Configuring MSFragger =====")
    msfrag_dir = software_dir / "MSFragger-4.4.1"
    
    if not msfrag_dir.exists():
        
        logger.warning("MSFragger requires manual download due to licensing. \n An academic email address is also required to download.")
        webbrowser.open("http://msfragger-upgrader.nesvilab.org/upgrader/")
        messagebox.showinfo("Action Required", f"Please select release 4.4.1 and fill in the form. \n\n A link to a zip file will be sent to your email. \n\n Add the zip to {software_dir}\n\nPress OK when complete.")
        logger.info("Manual download confirmed.")

    zip_path = software_dir / "MSFragger-4.4.1.zip"
    if zip_path:
        extract_archive(zip_path, software_dir, logger)
    else:
        logger.info("MaSpeQC will use Morpheus for proteomics QC")
        raise FileNotFoundError("MSFragger 4.4.1 archive not found.")
        

def setup_msbooster(software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring MSBooster =====")
    msboost_dir = software_dir / "MSBooster"
    
    if not msboost_dir.exists():
        msboost_dir.mkdir(exist_ok=True)
        jar_path = msboost_dir / "MSBooster-1.3.31.jar"
        download_file(MSBOOSTER_URL, jar_path, logger, progress_bar)  
        
def setup_percolator(software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring Percolator =====")
    percolator_dir = software_dir / "Percolator"
    
    if not percolator_dir.exists(): 
        percolator_dir.mkdir(exist_ok=True)                            
        exe_path = percolator_dir / "percolator.exe"
        download_file(PERCOLATOR_URL, exe_path, logger, progress_bar)

def setup_philosopher(software_dir: Path, logger, progress_bar):
    logger.info("\n===== Configuring Philosopher =====")
    phil_dir = software_dir / "Philosopher"
    if not phil_dir.exists():
        zip_path = software_dir / "philosopher_v5.1.0_windows_amd64.zip"
        download_file(PHILOSOPHER_URL, zip_path, logger, progress_bar)
        extract_archive(zip_path, phil_dir, logger)


# --- CustomTkinter GUI App ---
class MaSpeQCSetupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MaSpeQC 1.08 Setup")
        self.geometry("700x570")
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        self.header_label = ctk.CTkLabel(self, text="MaSpeQC Installation & Configuration", font=ctk.CTkFont(size=20, weight="bold"))
        self.header_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # Log Output (Text Box)
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")

        # Control Frame
        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew")
        self.control_frame.grid_columnconfigure(0, weight=1)

        # Added: CustomTkinter Progress Bar (spans horizontally across column 0)
        self.progress_bar = ctk.CTkProgressBar(self.control_frame, width=350)
        self.progress_bar.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.progress_bar.set(0.0) # Initialise at 0%

        self.start_btn = ctk.CTkButton(self.control_frame, text="Start Setup", command=self.start_setup)
        self.start_btn.grid(row=0, column=1, padx=10)

        self.exit_btn = ctk.CTkButton(self.control_frame, text="Exit", command=self.destroy, fg_color="gray40", hover_color="gray25")
        self.exit_btn.grid(row=0, column=2)

        # Logger Setup
        self.logger = logging.getLogger("MaSpeQC_Setup")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler("setup.log", mode='a')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(fh)
        
        # GUI handler
        gh = GUIHandler(self.log_textbox)
        gh.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(gh)

        # To handle GUI prompts from background threads
        self._gui_result = None
        self._gui_event = threading.Event()

    def wait_for_gui_input(self, gui_func):
        """Allows the worker thread to safely request user input via the main GUI thread."""
        self._gui_event.clear()
        
        def wrapper():
            self._gui_result = gui_func()
            self._gui_event.set()
            
        self.after(0, wrapper)
        self._gui_event.wait() # Block worker thread until GUI responds
        return self._gui_result

    def start_setup(self):
        self.start_btn.configure(state="disabled")
        self.logger.info("Initializing MaSpeQC 1.0 Setup...")
        
        # Run setup in a background thread to prevent UI freezing
        thread = threading.Thread(target=self.run_setup_tasks_test, daemon=True)
        thread.start()

    def run_setup_tasks(self):
        base_dir = Path.cwd()
        software_dir = base_dir / "Software"
        software_dir.mkdir(exist_ok=True)

        if not (base_dir / "mpmf-pipeline").exists() or not (base_dir / "mpmf-server").exists():
            self.logger.error("Error: Could not find MaSpeQC directories (mpmf-pipeline / mpmf-server).")
            self.logger.error("Please run this script from the root MaSpeQC folder.")
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            return

        status = {}
        
        try:
            setup_mysql(base_dir, software_dir, self.logger, self, self.progress_bar)
            status['MySQL'] = True
        except Exception as e:
            status['MySQL'] = False
            print(f"MySQL Setup Failed: {e}")
    
        try:
            setup_nodejs(base_dir, software_dir, self.logger, self.progress_bar)
            status['Node.js'] = True
        except Exception as e:
            status['Node.js'] = False
            print(f"Node.js Setup Failed: {e}")
    
        try:
            local_python = setup_local_python(software_dir, self.logger, self.progress_bar)
            setup_python_env(base_dir, local_python, self.logger)
            status['Python Environment'] = True
        except Exception as e:
            status['Python Environment'] = False
            print(f"Python Setup Failed: {e}")
    
        try:
            setup_mzmine(software_dir, self.logger, self.progress_bar)
            status['MZmine'] = True
        except Exception as e:
            status['MZmine'] = False
            print(f"MZmine Setup Failed: {e}")
    
        try:
            setup_morpheus(software_dir, self.logger, self.progress_bar)
            status['Morpheus'] = True
        except Exception as e:
            status['Morpheus'] = False
            print(f"Morpheus Setup Failed: {e}")
    
        try:
            setup_proteowizard(software_dir, self.logger)
            status['ProteoWizard'] = True
        except Exception as e:
            status['ProteoWizard'] = False
            print(f"ProteoWizard Setup Failed: {e}")

        try:
            setup_msfragger(software_dir, self.logger)
            status['MSFragger'] = True
        except Exception as e:
            status['MSFragger'] = False
            print(f"MSFragger Setup Failed: {e}")

        try:
            diann = setup_diann(software_dir, self.logger)
            if diann:
                status['DIA-NN'] = True
        except Exception as e:
            diann = False
            status['DIA-NN'] = False
            print(f"DIA-NN Setup Failed (MSBooster will be skipped): {e}")

        if diann: # MSBooster only if DIA-NN is installed
            try:
                setup_msbooster(software_dir, self.logger, self.progress_bar)
                status['MSBooster'] = True
            except Exception as e:
                status['MSBooster'] = False
                print(f"MSBooster Setup Failed: {e}")
    
        try:
            setup_percolator(software_dir, self.logger, self.progress_bar)
            status['Percolator'] = True
        except Exception as e:
            status['Percolator'] = False
            print(f"Percolator Setup Failed: {e}")

        try:
            setup_philosopher(software_dir, self.logger, self.progress_bar)
            status['Philosopher'] = True
        except Exception as e:
            status['Philosopher'] = False
            print(f"Philosopher Setup Failed: {e}")

        self.logger.info("\n===== Summary =====")
        for component, success in status.items():
            state = "Configured Successfully" if success else "Failed"
            self.logger.info(f"{component}: {state}")

        self.logger.info("\nSetup script finished.")
        self.after(0, lambda: self.start_btn.configure(text="Finished", state="disabled"))

    def run_setup_tasks_test(self):

        # modify this function to test individual components
        base_dir = Path.cwd()
        software_dir = base_dir / "Software"
        software_dir.mkdir(exist_ok=True)

        if not (base_dir / "mpmf-pipeline").exists() or not (base_dir / "mpmf-server").exists():
            self.logger.error("Error: Could not find MaSpeQC directories (mpmf-pipeline / mpmf-server).")
            self.logger.error("Please run this script from the root MaSpeQC folder.")
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            return

        status = {}
    
        try:
            diann = setup_diann(software_dir, self.logger)
            if diann:
                status['DIA-NN'] = True
        except Exception as e:
            diann = False
            status['DIA-NN'] = False
            print(f"DIA-NN Setup Failed (MSBooster will be skipped): {e}")

        if diann: # MSBooster only if DIA-NN is installed
            try:
                setup_msbooster(software_dir, self.logger, self.progress_bar)
                status['MSBooster'] = True
            except Exception as e:
                status['MSBooster'] = False
                print(f"MSBooster Setup Failed: {e}")


        self.logger.info("\n===== Summary =====")
        for component, success in status.items():
            state = "Configured Successfully" if success else "Failed"
            self.logger.info(f"{component}: {state}")

        self.logger.info("\nSetup script finished.")
        self.after(0, lambda: self.start_btn.configure(text="Finished", state="disabled"))

if __name__ == "__main__":
    app = MaSpeQCSetupApp()
    app.mainloop()
