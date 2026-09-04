import os
import sys
import json
import secrets
import string
import urllib.request
import zipfile
import tarfile
import subprocess
import time
import webbrowser
import logging
from pathlib import Path

# --- Configuration ---
PYTHON_MIN_VERSION = (3, 8)
PYTHON_MAX_VERSION = (3, 11)
DB_PORT = 3306
DELETE_DOWNLOADS = False

# URLs
MYSQL_URL = "https://dev.mysql.com/get/Downloads/MySQL-5.0/mysql-5.7.41-winx64.zip"
NODE_URL = "https://nodejs.org/dist/v18.20.4/node-v18.20.4-win-x64.zip"
PYTHON_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
MZMINE_URL = "https://github.com/mzmine/mzmine2/releases/download/v2.53/MZmine-2.53-Windows.zip"
MORPHEUS_URL = "https://github.com/cwenger/Morpheus/releases/download/r287/Morpheus_mzML.zip"

# --- Logging Setup ---
def setup_logger():
    logger = logging.getLogger("MaSpeQC_Setup")
    logger.setLevel(logging.DEBUG)

    # File Handler (Detailed with timestamps)
    fh = logging.FileHandler("setup.log", mode='a')
    fh.setLevel(logging.DEBUG)
    fh_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(fh_format)

    # Console Handler (Clean, mimics standard print)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch_format = logging.Formatter('%(message)s')
    ch.setFormatter(ch_format)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

logger = setup_logger()

def download_file(url: str, dest_path: Path):
    if not dest_path.exists():
        logger.info(f"Downloading {url}...")
        urllib.request.urlretrieve(url, dest_path)
    return dest_path

def extract_archive(archive_path: Path, dest_dir: Path):
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

def run_cmd(args, cwd=None, check=True, capture=False, new_console=False):
    kwargs = {'cwd': cwd, 'check': check}
    if capture:
        kwargs.update({'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'text': True})
    
    if new_console and sys.platform == "win32":
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
        
    logger.debug(f"Running command: {' '.join(str(a) for a in args)}")
    return subprocess.run(args, **kwargs)

def setup_mysql(base_dir: Path, software_dir: Path):
    logger.info("\n===== Configuring MySQL Community Server =====")
    mysql_dir = software_dir / "mysql-5.7.41-winx64"
    mysql_bin = mysql_dir / "bin"
    
    if not mysql_dir.exists():
        zip_path = software_dir / "mysql-5.7.41-winx64.zip"
        download_file(MYSQL_URL, zip_path)
        extract_archive(zip_path, software_dir)

    data_dir = base_dir / "data"
    my_cnf = mysql_dir / "my.cnf"

    if not data_dir.exists():
        logger.info("Creating data directory and configuration...")
        data_dir.mkdir(parents=True)
        
        my_cnf.write_text(f"""[mysqld]
basedir="{mysql_dir.as_posix()}"
datadir="{data_dir.as_posix()}"
port={DB_PORT}
explicit-defaults-for-timestamp=ON
log-syslog=OFF
tls_version=TLSv1.2

[client]
port={DB_PORT}
""")

        db_config = {"Database Port": DB_PORT, "Database Name": "maspeqc", "User": "maspeqc"}
        for target in [base_dir / "mpmf-pipeline" / "Config" / "database-login.json", 
                       base_dir / "mpmf-server" / "database-login.json"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, 'w') as f:
                json.dump(db_config, f)

        logger.info("Initializing MySQL server...")
        run_cmd([mysql_bin / "mysqld.exe", "--initialize-insecure", "--console"])

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
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "CREATE DATABASE maspeqc;"])

        chars = string.ascii_letters + string.digits
        password = "".join(secrets.choice(chars) for _ in range(16))
        
        (base_dir / "mpmf-pipeline" / "Config" / ".maspeqc_gen").write_text(password)
        (base_dir / "mpmf-server" / ".maspeqc_gen").write_text(password)

        logger.info("Creating user and setting privileges...")
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", 
                 f"CREATE USER 'maspeqc'@'localhost' IDENTIFIED BY '{password}';"])
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", 
                 "GRANT ALL PRIVILEGES ON `maspeqc`.* TO `maspeqc`@`localhost`; FLUSH PRIVILEGES;"])
        
        logger.info("\n*** ACTION REQUIRED ***")
        logger.info("Please enter a new database password for the 'root' user when prompted:")
        run_cmd([mysql_bin / "mysqladmin.exe", "-u", "root", "password"])

def setup_nodejs(base_dir: Path, software_dir: Path):
    logger.info("\n===== Configuring Node.js =====")
    node_dir = software_dir / "node-v18.20.4-win-x64"
    
    if not node_dir.exists():
        zip_path = software_dir / "node-v18.20.4-win-x64.zip"
        download_file(NODE_URL, zip_path)
        extract_archive(zip_path, software_dir)

    server_dir = base_dir / "mpmf-server"
    if server_dir.exists() and not (server_dir / "node_modules").exists():
        logger.info("Installing Node modules...")
        
        env = os.environ.copy()
        env["PATH"] = f"{node_dir};{env['PATH']}"
        
        run_cmd([node_dir / "npm.cmd", "install"], cwd=server_dir)
        
        logger.info("Starting Node.js configuration server...")
        subprocess.Popen(f'"{node_dir / "npm.cmd"}" start --setup', cwd=server_dir, env=env, 
                         shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        logger.info("Opening browser for configuration...")
        time.sleep(3) 
        webbrowser.open("http://localhost/configuration")
        input("Press Enter once you have completed the browser configuration...")
        logger.info("Browser configuration completed.")

def setup_python_env(base_dir: Path, software_dir: Path):
    logger.info("\n===== Configuring Python =====")
    if sys.version_info < PYTHON_MIN_VERSION or sys.version_info > PYTHON_MAX_VERSION:
        logger.warning(f"Warning: Current Python is {sys.version_info.major}.{sys.version_info.minor}.")
        logger.warning("The batch script expected 3.8 to 3.11. Proceeding anyway, but be aware.")

    pipeline_dir = base_dir / "mpmf-pipeline"
    venv_dir = pipeline_dir / ".venv"
    
    if pipeline_dir.exists() and not venv_dir.exists():
        logger.info("Creating virtual environment...")
        run_cmd([sys.executable, "-m", "venv", ".venv"], cwd=pipeline_dir)
        
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        
        logger.info("Installing Python requirements...")
        run_cmd([pip_exe, "install", "-r", "requirements.txt"], cwd=pipeline_dir)
        
        if (pipeline_dir / "Config" / ".maspeqc_gen").exists():
            logger.info("Running MPMF_Database_SetUp.py...")
            run_cmd([python_exe, "MPMF_Database_SetUp.py"], cwd=pipeline_dir)

def setup_mzmine(software_dir: Path):
    logger.info("\n===== Configuring MZmine =====")
    mzmine_dir = software_dir / "MZmine-2.53-Windows"
    
    if not mzmine_dir.exists():
        zip_path = software_dir / "MZmine-2.53-Windows.zip"
        download_file(MZMINE_URL, zip_path)
        extract_archive(zip_path, software_dir)
        
    logger.info("Testing MZmine launch (Please close MZmine once it opens)...")
    run_cmd([mzmine_dir / "bin" / "java.exe", "-classpath", "lib\\*", "io.github.mzmine.main.MZmineCore"], cwd=mzmine_dir)

def setup_morpheus(software_dir: Path):
    logger.info("\n===== Configuring Morpheus =====")
    morpheus_dir = software_dir / "Morpheus (mzML)"
    
    if not morpheus_dir.exists():
        zip_path = software_dir / "Morpheus_mzML.zip"
        download_file(MORPHEUS_URL, zip_path)
        extract_archive(zip_path, software_dir)

def setup_proteowizard(software_dir: Path):
    logger.info("\n===== Configuring ProteoWizard (msconvert) =====")
    pwiz_dir = software_dir / "ProteoWizard"
    
    if not pwiz_dir.exists():
        tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
        if not tar_files:
            logger.warning("ProteoWizard requires manual download due to licensing.")
            webbrowser.open("https://proteowizard.sourceforge.io/download.html")
            input(f"Please download the 'Windows 64-bit tar.bz2' to {software_dir} and press Enter...")
            logger.info("Manual download confirmed.")
            tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
            
        if tar_files:
            pwiz_dir.mkdir(exist_ok=True)
            extract_archive(tar_files[0], pwiz_dir)
            logger.info("Extracted ProteoWizard.")
        else:
            raise FileNotFoundError("ProteoWizard archive not found.")

def main():
    logger.info("MaSpeQC 1.0 Python Setup Script Started")
    if input("Do you want to continue (y/n)? ").lower() != 'y':
        logger.info("Setup aborted by user.")
        sys.exit(0)

    base_dir = Path.cwd()
    software_dir = base_dir / "Software"
    software_dir.mkdir(exist_ok=True)

    if not (base_dir / "mpmf-pipeline").exists() or not (base_dir / "mpmf-server").exists():
        logger.error("Could not find MaSpeQC 1.0 directories. Ensure you are running this in the correct folder.")
        sys.exit(1)

    status = {}
    
    # Executing steps with error capturing
    steps = [
        ("MySQL", setup_mysql, (base_dir, software_dir)),
        ("Node.js", setup_nodejs, (base_dir, software_dir)),
        ("Python Environment", setup_python_env, (base_dir, software_dir)),
        ("MZmine", setup_mzmine, (software_dir,)),
        ("Morpheus", setup_morpheus, (software_dir,)),
        ("ProteoWizard", setup_proteowizard, (software_dir,))
    ]

    for name, func, args in steps:
        try:
            func(*args)
            status[name] = True
        except Exception as e:
            status[name] = False
            logger.error(f"{name} Setup Failed: {e}", exc_info=True) # exc_info writes full stack trace to log

    logger.info("\n===== Summary =====")
    for component, success in status.items():
        state = "Configured Successfully" if success else "Failed"
        logger.info(f"{component}: {state}")

    logger.info("Setup script finished.")

if __name__ == "__main__":
    main()