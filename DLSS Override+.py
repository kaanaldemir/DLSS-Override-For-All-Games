import sys, os, json, shutil, stat, getpass, hashlib, subprocess, ctypes
from PyQt6 import QtWidgets, QtGui, QtCore

# Mapping of full DLSS override key names to short labels for display.
KEY_MAPPING = {
    "Disable_FG_Override": "FG",
    "Disable_RR_Override": "RR",
    "Disable_SR_Override": "SR",
    "Disable_RR_Model_Override": "RR-M",
    "Disable_SR_Model_Override": "SR-M",
}

# Computes the SHA-256 hash of a file's contents.
def compute_file_hash(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            # Read file in chunks of 8192 bytes
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception as e:
        print(f"Error computing hash: {e}")
    return h.hexdigest()

# Creates a backup copy of the given file and writes its hash metadata to a JSON file.
def create_backup(main_path, backup_path, meta_path, log_func):
    try:
        shutil.copy2(main_path, backup_path)  # Copy the file with metadata preservation
        original_hash = compute_file_hash(main_path)
        # Create metadata with both original and modified hash set to original hash
        meta = {"original_hash": original_hash, "modified_hash": original_hash}
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        log_func(f"No backup found, creating new backup.\nBackup created at: {backup_path}")
        return meta
    except Exception as e:
        log_func(f"Error creating backup: {e}")
        return None

# Loads backup metadata from the specified meta file.
def load_backup_meta(meta_path):
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta
    except Exception:
        return None

# Saves the provided metadata to the specified meta file.
def save_backup_meta(meta_path, meta):
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except Exception as e:
        print(f"Error saving backup meta: {e}")

# Checks if the existing backup is obsolete (i.e. the file has been modified externally).
# If so, it creates a new backup.
def update_backup_if_obsolete(main_path, backup_path, meta_path, log_func):
    if not os.path.exists(backup_path) or not os.path.exists(meta_path):
        return create_backup(main_path, backup_path, meta_path, log_func)
    meta = load_backup_meta(meta_path)
    if meta is None:
        log_func("Backup meta is invalid, creating new backup.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    current_hash = compute_file_hash(main_path)
    if current_hash != meta["modified_hash"]:
        log_func("External update detected. Updating backup to current file as new baseline.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    return meta

# Recursively traverses the JSON object, flipping any DLSS override keys set to True to False.
# It also logs which keys (abbreviated) were changed, storing them in the updates dictionary.
def recursive_process(obj, keys_to_update, updates):
    modified = False
    if isinstance(obj, dict):
        for key in keys_to_update:
            if key in obj and obj[key] is True:
                obj[key] = False  # Flip the key value to False
                modified = True
                identifier = obj.get("LocalId") or obj.get("DisplayName") or "Unknown"
                updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        if "Application" in obj and isinstance(obj["Application"], dict):
            for key in keys_to_update:
                if key in obj["Application"] and obj["Application"][key] is True:
                    obj["Application"][key] = False
                    modified = True
                    identifier = obj["Application"].get("DisplayName") or obj.get("LocalId") or "Unknown"
                    updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        for value in obj.values():
            if isinstance(value, (dict, list)):
                if recursive_process(value, keys_to_update, updates):
                    modified = True
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                if recursive_process(item, keys_to_update, updates):
                    modified = True
    return modified

# Reads the JSON file, processes it to update DLSS keys, writes changes back, and updates metadata.
def modify_file(main_path, log_func):
    backup_path = main_path + ".backup"
    meta_path = main_path + ".backup.meta"
    meta = update_backup_if_obsolete(main_path, backup_path, meta_path, log_func)
    try:
        with open(main_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log_func(f"Error reading JSON: {e}")
        return False, None
    keys_to_update = list(KEY_MAPPING.keys())
    updates = {}
    modified = recursive_process(data, keys_to_update, updates)
    if modified:
        try:
            with open(main_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            log_func("File has been updated.")
            mod_hash = compute_file_hash(main_path)
            meta["modified_hash"] = mod_hash
            save_backup_meta(meta_path, meta)
        except Exception as e:
            log_func(f"Error writing JSON: {e}")
            return False, None
    else:
        log_func("No modifications were made. Either keys were not found or already set to False.")
    # Log a summary of changes per application.
    for app, changes in updates.items():
        summary = ", ".join(f"{abbr} ✓" for abbr in sorted(changes))
        log_func(f"{app}: {summary}")
    if modified:
        log_func("Reboot recommended for changes to take effect.")
    return modified, meta

# Reverts the file to its backup version if it hasn't been modified externally.
def revert_file(main_path, log_func):
    backup_path = main_path + ".backup"
    meta_path = main_path + ".backup.meta"
    if not os.path.exists(backup_path) or not os.path.exists(meta_path):
        log_func("No backup available to revert.")
        return False
    meta = load_backup_meta(meta_path)
    current_hash = compute_file_hash(main_path)
    if current_hash != meta["modified_hash"]:
        log_func("Cannot revert: file has been externally modified since our last update.")
        return False
    try:
        os.chmod(main_path, stat.S_IWRITE)
        shutil.copy2(backup_path, main_path)
        log_func("Reverted to backup.")
        meta["modified_hash"] = meta["original_hash"]
        save_backup_meta(meta_path, meta)
        return True
    except Exception as e:
        log_func(f"Error during revert: {e}")
        return False

# Attempts to restart NVIDIA services. Runs the command with elevated rights if needed.
# The command is run hidden and its output is captured and logged.
def restart_services(log_func):
    cmd = '/c net stop "NvContainerLocalSystem" && net start "NvContainerLocalSystem" && net stop "NVDisplay.ContainerLocalSystem" && net start "NVDisplay.ContainerLocalSystem"'
    # Check if user is admin
    if ctypes.windll.shell32.IsUserAnAdmin():
        result = subprocess.run("cmd.exe " + cmd, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, text=True, encoding='utf-8', errors='replace')
        log_func("Restart Services Output:")
        log_func(result.stdout)
        if result.stderr:
            log_func("Errors:")
            log_func(result.stderr)
    else:
        # If not admin, this call will trigger a UAC prompt while keeping the window hidden.
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmd, None, 0)
        if ret <= 32:
            log_func("Failed to launch elevated command for restarting services.")
        else:
            log_func("Restart services command launched. Windows should prompt for admin rights.")

# Custom dialog that presents the user with three options: Restart Services, Reboot, or Do Nothing.
class CloseActionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Action Required")
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel("Changes require a reboot or service restart to take effect.\nWhat would you like to do?")
        layout.addWidget(label)
        buttonLayout = QtWidgets.QHBoxLayout()
        # Add the Restart Services button (with shield emoji) on the left
        self.restartButton = QtWidgets.QPushButton("🛡️ Restart Services")
        self.rebootButton = QtWidgets.QPushButton("Reboot")
        self.noActionButton = QtWidgets.QPushButton("Do Nothing")
        # Arrange buttons: Restart Services (left), Reboot (middle), Do Nothing (right)
        buttonLayout.addWidget(self.restartButton)
        buttonLayout.addWidget(self.rebootButton)
        buttonLayout.addWidget(self.noActionButton)
        layout.addLayout(buttonLayout)
        # Connect each button to return a distinct integer value
        self.restartButton.clicked.connect(lambda: self.done(1))
        self.rebootButton.clicked.connect(lambda: self.done(2))
        self.noActionButton.clicked.connect(lambda: self.done(0))

# Main application window class.
class DLSSOverrideApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DLSS Override Editor")
        self.resize(800, 400)
        self.session_processed = False  # Tracks if any changes were made in the current session.
        self.setup_ui()
        self.apply_dark_theme()

    # Set up UI elements: file path input, buttons, and log display.
    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        username = getpass.getuser()
        default_path = fr"C:\Users\{username}\AppData\Local\NVIDIA Corporation\NVIDIA app\NvBackend\ApplicationStorage.json"
        self.path_edit.setText(default_path)
        path_layout.addWidget(self.path_edit)
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_file)
        path_layout.addWidget(self.browse_button)
        layout.addLayout(path_layout)
        self.readonly_checkbox = QtWidgets.QCheckBox("Set file as read-only after modifications")
        self.readonly_checkbox.setChecked(True)
        layout.addWidget(self.readonly_checkbox)
        btn_layout = QtWidgets.QHBoxLayout()
        self.process_button = QtWidgets.QPushButton("Process")
        self.process_button.clicked.connect(self.process_file)
        btn_layout.addWidget(self.process_button)
        self.revert_button = QtWidgets.QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert_file)
        btn_layout.addWidget(self.revert_button)
        layout.addLayout(btn_layout)
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    # Applies a dark theme with blue accents.
    def apply_dark_theme(self):
        style = """
        QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
            font-family: "Segoe UI", sans-serif;
        }
        QLineEdit, QTextEdit {
            background-color: #2d2d30;
            border: 1px solid #3e3e42;
            padding: 5px;
            border-radius: 3px;
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #007ACC;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            color: #ffffff;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #005A9E;
        }
        QPushButton:pressed {
            background-color: #003F73;
        }
        QCheckBox {
            spacing: 5px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }
        QCheckBox::indicator:unchecked {
            border: 1px solid #555555;
            background-color: #2d2d30;
        }
        QCheckBox::indicator:checked {
            border: 1px solid #007ACC;
            background-color: #007ACC;
        }
        """
        self.setStyleSheet(style)

    # Appends a message to the log display.
    def log(self, message):
        self.log_text.append(message)

    # Opens a file dialog for the user to select the JSON file.
    def browse_file(self):
        current_path = self.path_edit.text().strip()
        initial_dir = os.path.dirname(current_path) if os.path.exists(current_path) else ""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select ApplicationStorage.json file", initial_dir, "JSON Files (*.json);;All Files (*)")
        if file_path:
            self.path_edit.setText(file_path)

    # Processes the file by calling modify_file and sets the session flag.
    def process_file(self):
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(self, "Confirm", f"Are you sure you want to modify this file?\n{file_path}",
                                                 QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.log("Operation cancelled by user.")
            return
        modified, _ = modify_file(file_path, self.log)
        if modified:
            self.session_processed = True
        if modified and self.readonly_checkbox.isChecked():
            try:
                os.chmod(file_path, stat.S_IREAD)
                self.log("File set to read-only.")
            except Exception as e:
                self.log(f"Error setting file to read-only: {e}")

    # Reverts the file to its backup state and updates the session flag.
    def revert_file(self):
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(self, "Confirm Revert", f"Are you sure you want to revert changes to this file?\n{file_path}",
                                                 QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.log("Revert cancelled by user.")
            return
        if revert_file(file_path, self.log):
            self.log("Revert successful.")
            if self.session_processed:
                self.session_processed = False
            else:
                self.session_processed = True
        else:
            self.log("Revert failed or no valid backup available.")

    # When closing, if changes were made, prompt the user with a custom dialog that offers:
    # 1. Restart Services (left button)
    # 2. Reboot (middle button)
    # 3. Do Nothing (right button)
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.session_processed:
            dialog = CloseActionDialog(self)
            result = dialog.exec()
            if result == 1:
                restart_services(self.log)
            elif result == 2:
                os.system("shutdown /r /t 0")
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = DLSSOverrideApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
