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

def download_file(url: str, dest_path: Path):
    if not dest_path.exists():
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, dest_path)
    return dest_path

def extract_archive(archive_path: Path, dest_dir: Path):
    print(f"Extracting {archive_path.name}...")
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
    elif archive_path.name.endswith(".tar.bz2") or archive_path.name.endswith(".tar"):
        with tarfile.open(archive_path, "r:*") as tar_ref:
            tar_ref.extractall(dest_dir)
    
    if DELETE_DOWNLOADS:
        archive_path.unlink()

def run_cmd(args, cwd=None, check=True, capture=False, new_console=False):
    kwargs = {'cwd': cwd, 'check': check}
    if capture:
        kwargs.update({'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'text': True})
    
    # Windows specific flag to launch in a new console window (like batch `start`)
    if new_console and sys.platform == "win32":
        kwargs['creationflags'] = subprocess.CREATE_NEW_CONSOLE
        
    return subprocess.run(args, **kwargs)

def setup_mysql(base_dir: Path, software_dir: Path):
    print("\n===== Configuring MySQL Community Server =====")
    mysql_dir = software_dir / "mysql-5.7.41-winx64"
    mysql_bin = mysql_dir / "bin"
    
    if not mysql_dir.exists():
        zip_path = software_dir / "mysql-5.7.41-winx64.zip"
        download_file(MYSQL_URL, zip_path)
        extract_archive(zip_path, software_dir)

    data_dir = base_dir / "data"
    my_cnf = mysql_dir / "my.cnf"

    if not data_dir.exists():
        print("Creating data directory and configuration...")
        data_dir.mkdir(parents=True)
        
        # Write my.cnf
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

        # Write Database JSONs
        db_config = {"Database Port": DB_PORT, "Database Name": "maspeqc", "User": "maspeqc"}
        for target in [base_dir / "mpmf-pipeline" / "Config" / "database-login.json", 
                       base_dir / "mpmf-server" / "database-login.json"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, 'w') as f:
                json.dump(db_config, f)

        # Initialize Server
        print("Initializing MySQL server...")
        run_cmd([mysql_bin / "mysqld.exe", "--initialize-insecure", "--console"])

    # Start Server
    print("Starting MySQL server in a new window...")
    subprocess.Popen([mysql_bin / "mysqld.exe", "--console"], creationflags=subprocess.CREATE_NEW_CONSOLE)
    
    # Poll for server readiness
    print("Waiting for MySQL server to become ready...")
    for _ in range(30):
        result = run_cmd([mysql_bin / "mysqladmin.exe", "-s", "ping"], check=False, capture=True)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("MySQL server failed to start or respond to ping.")

    # Check and Create Database
    result = run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "SHOW DATABASES LIKE 'maspeqc';"], capture=True)
    if "maspeqc" not in result.stdout:
        print("Creating database 'maspeqc'...")
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", "CREATE DATABASE maspeqc;"])

        # Generate Password and Create User
        chars = string.ascii_letters + string.digits
        password = "".join(secrets.choice(chars) for _ in range(16))
        
        (base_dir / "mpmf-pipeline" / "Config" / ".maspeqc_gen").write_text(password)
        (base_dir / "mpmf-server" / ".maspeqc_gen").write_text(password)

        print("Creating user and setting privileges...")
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", 
                 f"CREATE USER 'maspeqc'@'localhost' IDENTIFIED BY '{password}';"])
        run_cmd([mysql_bin / "mysql", "-u", "root", "-e", 
                 "GRANT ALL PRIVILEGES ON `maspeqc`.* TO `maspeqc`@`localhost`; FLUSH PRIVILEGES;"])
        
        print("\n*** ACTION REQUIRED ***")
        print("Please enter a new database password for the 'root' user when prompted:")
        run_cmd([mysql_bin / "mysqladmin.exe", "-u", "root", "password"])

def setup_nodejs(base_dir: Path, software_dir: Path):
    print("\n===== Configuring Node.js =====")
    node_dir = software_dir / "node-v18.20.4-win-x64"
    
    if not node_dir.exists():
        zip_path = software_dir / "node-v18.20.4-win-x64.zip"
        download_file(NODE_URL, zip_path)
        extract_archive(zip_path, software_dir)

    server_dir = base_dir / "mpmf-server"
    if server_dir.exists() and not (server_dir / "node_modules").exists():
        print("Installing Node modules...")
        
        # Inject Node into PATH for this process
        env = os.environ.copy()
        env["PATH"] = f"{node_dir};{env['PATH']}"
        
        run_cmd([node_dir / "npm.cmd", "install"], cwd=server_dir)
        
        print("Starting Node.js configuration server...")
        # Use shell=True for npm.cmd in a new console
        subprocess.Popen(f'"{node_dir / "npm.cmd"}" start --setup', cwd=server_dir, env=env, 
                         shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        print("Opening browser for configuration...")
        time.sleep(3) # Give server a moment to bind
        webbrowser.open("http://localhost/configuration")
        input("Press Enter once you have completed the browser configuration...")

def setup_python_env(base_dir: Path, software_dir: Path):
    print("\n===== Configuring Python =====")
    # Check current Python version. We assume the running interpreter is the one to use,
    # as the user launched this script with it.
    if sys.version_info < PYTHON_MIN_VERSION or sys.version_info > PYTHON_MAX_VERSION:
        print(f"Warning: Current Python is {sys.version_info.major}.{sys.version_info.minor}.")
        print("The batch script expected 3.8 to 3.11. Proceeding anyway, but be aware.")

    pipeline_dir = base_dir / "mpmf-pipeline"
    venv_dir = pipeline_dir / ".venv"
    
    if pipeline_dir.exists() and not venv_dir.exists():
        print("Creating virtual environment...")
        run_cmd([sys.executable, "-m", "venv", ".venv"], cwd=pipeline_dir)
        
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
        
        print("Installing Python requirements...")
        run_cmd([pip_exe, "install", "-r", "requirements.txt"], cwd=pipeline_dir)
        
        if (pipeline_dir / "Config" / ".maspeqc_gen").exists():
            print("Running MPMF_Database_SetUp.py...")
            run_cmd([python_exe, "MPMF_Database_SetUp.py"], cwd=pipeline_dir)

def setup_mzmine(software_dir: Path):
    print("\n===== Configuring MZmine =====")
    mzmine_dir = software_dir / "MZmine-2.53-Windows"
    
    if not mzmine_dir.exists():
        zip_path = software_dir / "MZmine-2.53-Windows.zip"
        download_file(MZMINE_URL, zip_path)
        extract_archive(zip_path, software_dir)
        
    print("Testing MZmine launch (Please close MZmine once it opens)...")
    run_cmd([mzmine_dir / "bin" / "java.exe", "-classpath", "lib\\*", "io.github.mzmine.main.MZmineCore"], cwd=mzmine_dir)

def setup_morpheus(software_dir: Path):
    print("\n===== Configuring Morpheus =====")
    morpheus_dir = software_dir / "Morpheus (mzML)"
    
    if not morpheus_dir.exists():
        zip_path = software_dir / "Morpheus_mzML.zip"
        download_file(MORPHEUS_URL, zip_path)
        extract_archive(zip_path, software_dir)

def setup_proteowizard(software_dir: Path):
    print("\n===== Configuring ProteoWizard (msconvert) =====")
    pwiz_dir = software_dir / "ProteoWizard"
    
    if not pwiz_dir.exists():
        tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
        if not tar_files:
            print("ProteoWizard requires manual download due to licensing.")
            webbrowser.open("https://proteowizard.sourceforge.io/download.html")
            input(f"Please download the 'Windows 64-bit tar.bz2' to {software_dir} and press Enter...")
            tar_files = list(software_dir.glob("pwiz-bin-*.tar.bz2"))
            
        if tar_files:
            # Native Python BZ2/TAR extraction eliminates the need for the bzip2 Windows binary!
            pwiz_dir.mkdir(exist_ok=True)
            extract_archive(tar_files[0], pwiz_dir)
            print("Extracted ProteoWizard.")
        else:
            raise FileNotFoundError("ProteoWizard archive not found.")

def main():
    print("MaSpeQC 1.0 Python Setup Script")
    if input("Do you want to continue (y/n)? ").lower() != 'y':
        sys.exit(0)

    base_dir = Path.cwd()
    software_dir = base_dir / "Software"
    software_dir.mkdir(exist_ok=True)

    if not (base_dir / "mpmf-pipeline").exists() or not (base_dir / "mpmf-server").exists():
        print("Error: Could not find MaSpeQC 1.0 directories. Ensure you are running this in the correct folder.")
        sys.exit(1)

    status = {}
    
    try:
        setup_mysql(base_dir, software_dir)
        status['MySQL'] = True
    except Exception as e:
        status['MySQL'] = False
        print(f"MySQL Setup Failed: {e}")

    try:
        setup_nodejs(base_dir, software_dir)
        status['Node.js'] = True
    except Exception as e:
        status['Node.js'] = False
        print(f"Node.js Setup Failed: {e}")

    try:
        setup_python_env(base_dir, software_dir)
        status['Python Environment'] = True
    except Exception as e:
        status['Python Environment'] = False
        print(f"Python Setup Failed: {e}")

    try:
        setup_mzmine(software_dir)
        status['MZmine'] = True
    except Exception as e:
        status['MZmine'] = False
        print(f"MZmine Setup Failed: {e}")

    try:
        setup_morpheus(software_dir)
        status['Morpheus'] = True
    except Exception as e:
        status['Morpheus'] = False
        print(f"Morpheus Setup Failed: {e}")

    try:
        setup_proteowizard(software_dir)
        status['ProteoWizard'] = True
    except Exception as e:
        status['ProteoWizard'] = False
        print(f"ProteoWizard Setup Failed: {e}")

    print("\n===== Summary =====")
    for component, success in status.items():
        state = "Configured Successfully" if success else "Failed"
        print(f"{component}: {state}")

if __name__ == "__main__":
    main()
