import sys, os, json, shutil, stat, getpass, hashlib
# Import standard libraries for system interaction, file handling, JSON parsing,
# file copying, file permissions, user info retrieval, and hashing.
from PyQt6 import QtWidgets, QtGui, QtCore
# Import PyQt6 modules for building the graphical user interface.

# Mapping from JSON override keys to their abbreviated representations for logging.
KEY_MAPPING = {
    "Disable_FG_Override": "FG",
    "Disable_RR_Override": "RR",
    "Disable_SR_Override": "SR",
    "Disable_RR_Model_Override": "RR-M",
    "Disable_SR_Model_Override": "SR-M",
}

def compute_file_hash(path):
    """
    Computes the SHA-256 hash of the file at the given path.
    Reads the file in chunks to handle large files without loading everything into memory.
    
    Args:
        path (str): Path to the file.
        
    Returns:
        str: Hexadecimal digest of the file's hash.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            # Read the file in 8KB chunks.
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception as e:
        print(f"Error computing hash: {e}")
    return h.hexdigest()

def create_backup(main_path, backup_path, meta_path, log_func):
    """
    Creates a backup of the main file and saves metadata including the file hash.
    
    Steps:
      - Copies the main file to backup_path.
      - Computes its hash and stores it as both the original and modified hash in meta.
      - Logs the backup creation.
    
    Args:
        main_path (str): Path of the original file.
        backup_path (str): Path where the backup will be stored.
        meta_path (str): Path to store the backup metadata JSON.
        log_func (function): Logging function to output messages.
    
    Returns:
        dict or None: The metadata dictionary if backup is created, otherwise None.
    """
    try:
        # Create a backup copy preserving metadata.
        shutil.copy2(main_path, backup_path)
        original_hash = compute_file_hash(main_path)
        meta = {"original_hash": original_hash, "modified_hash": original_hash}
        # Write metadata to the meta file.
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        log_func(f"No backup found, creating new backup.\nBackup created at: {backup_path}")
        return meta
    except Exception as e:
        log_func(f"Error creating backup: {e}")
        return None

def load_backup_meta(meta_path):
    """
    Loads backup metadata from the JSON file at meta_path.
    
    Args:
        meta_path (str): Path to the metadata file.
        
    Returns:
        dict or None: The metadata if successfully loaded; otherwise, None.
    """
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta
    except Exception:
        return None

def save_backup_meta(meta_path, meta):
    """
    Saves the provided metadata dictionary to the specified meta_path.
    
    Args:
        meta_path (str): Path to store the metadata.
        meta (dict): Metadata to be saved.
    """
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except Exception as e:
        print(f"Error saving backup meta: {e}")

def update_backup_if_obsolete(main_path, backup_path, meta_path, log_func):
    """
    Checks if the backup exists and is up-to-date with the main file.
    If the backup is missing or the main file has changed externally,
    a new backup is created.
    
    Args:
        main_path (str): Path to the main file.
        backup_path (str): Path to the backup file.
        meta_path (str): Path to the metadata file.
        log_func (function): Logging function to output messages.
    
    Returns:
        dict: The (possibly updated) metadata.
    """
    # Create a new backup if either backup or meta file doesn't exist.
    if not os.path.exists(backup_path) or not os.path.exists(meta_path):
        return create_backup(main_path, backup_path, meta_path, log_func)
    meta = load_backup_meta(meta_path)
    if meta is None:
        log_func("Backup meta is invalid, creating new backup.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    current_hash = compute_file_hash(main_path)
    # If the main file's current hash doesn't match the stored modified hash,
    # it means an external change occurred.
    if current_hash != meta["modified_hash"]:
        log_func("External update detected. Updating backup to current file as new baseline.")
        return create_backup(main_path, backup_path, meta_path, log_func)
    return meta

def recursive_process(obj, keys_to_update, updates):
    """
    Recursively searches through the JSON object (which can contain nested dictionaries or lists)
    for specified keys. If a key is found with a True value, it is set to False.
    The function also collects an update log per item, using an identifier from the object.
    
    Args:
        obj (dict or list): The JSON object to process.
        keys_to_update (list): Keys to look for and update.
        updates (dict): Dictionary to record which keys have been modified.
    
    Returns:
        bool: True if any modification was made, False otherwise.
    """
    modified = False
    if isinstance(obj, dict):
        # Check each key in the current dictionary.
        for key in keys_to_update:
            if key in obj and obj[key] is True:
                obj[key] = False  # Modify the value to False.
                modified = True
                # Use available fields as an identifier (LocalId or DisplayName).
                identifier = obj.get("LocalId") or obj.get("DisplayName") or "Unknown"
                updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        # Specifically process the 'Application' nested dictionary if it exists.
        if "Application" in obj and isinstance(obj["Application"], dict):
            for key in keys_to_update:
                if key in obj["Application"] and obj["Application"][key] is True:
                    obj["Application"][key] = False
                    modified = True
                    identifier = obj["Application"].get("DisplayName") or obj.get("LocalId") or "Unknown"
                    updates.setdefault(identifier, set()).add(KEY_MAPPING.get(key, key))
        # Recursively process each value in the dictionary.
        for value in obj.values():
            if isinstance(value, (dict, list)):
                if recursive_process(value, keys_to_update, updates):
                    modified = True
    elif isinstance(obj, list):
        # Process each item in the list if it is a dictionary or list.
        for item in obj:
            if isinstance(item, (dict, list)):
                if recursive_process(item, keys_to_update, updates):
                    modified = True
    return modified

def modify_file(main_path, log_func):
    """
    Modifies the JSON file at main_path by setting specific boolean override keys from True to False.
    
    Process:
      - Ensures an up-to-date backup exists.
      - Loads the JSON file.
      - Recursively updates keys (using recursive_process).
      - Writes the updated JSON back to the file if changes occurred.
      - Updates backup metadata with the new file hash.
      - Logs a summary of the modifications.
    
    Args:
        main_path (str): Path to the main JSON file.
        log_func (function): Function to log messages.
    
    Returns:
        tuple: (modified (bool), meta (dict)) indicating if changes were made and the backup metadata.
    """
    backup_path = main_path + ".backup"
    meta_path = main_path + ".backup.meta"
    # Update or create backup if needed.
    meta = update_backup_if_obsolete(main_path, backup_path, meta_path, log_func)
    try:
        with open(main_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log_func(f"Error reading JSON: {e}")
        return False, None
    keys_to_update = list(KEY_MAPPING.keys())
    updates = {}
    # Recursively process the JSON data to update keys.
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
    # Log a summary for each modified application.
    for app, changes in updates.items():
        summary = ", ".join(f"{abbr} ✓" for abbr in sorted(changes))
        log_func(f"{app}: {summary}")
    if modified:
        log_func("Reboot recommended for changes to take effect.")
    return modified, meta

def revert_file(main_path, log_func):
    """
    Reverts the main JSON file back to its backup version.
    
    The function checks if a backup and its metadata exist and ensures that the file
    has not been externally modified since the last update. If all checks pass, the backup
    is restored.
    
    Args:
        main_path (str): Path to the main JSON file.
        log_func (function): Function to log messages.
    
    Returns:
        bool: True if revert was successful, False otherwise.
    """
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
        # Remove read-only attribute by setting the file as writable.
        os.chmod(main_path, stat.S_IWRITE)
        # Restore the backup file.
        shutil.copy2(backup_path, main_path)
        log_func("Reverted to backup.")
        meta["modified_hash"] = meta["original_hash"]
        save_backup_meta(meta_path, meta)
        return True
    except Exception as e:
        log_func(f"Error during revert: {e}")
        return False

class DLSSOverrideApp(QtWidgets.QMainWindow):
    """
    Main window for the DLSS Override Editor application.
    
    Provides a graphical interface to:
      - Browse and select the JSON file.
      - Process modifications on the file.
      - Revert changes from backup.
      - Set the file as read-only post-modification.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DLSS Override Editor")
        self.resize(800, 400)
        self.session_processed = False  # Tracks whether modifications were made this session.
        self.setup_ui()              # Build the GUI components.
        self.apply_dark_theme()      # Apply a dark theme to the interface.

    def setup_ui(self):
        """
        Constructs the user interface layout including file path entry, buttons, checkbox, and log area.
        """
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        
        # Layout for the file path input and browse button.
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        # Use the current user's directory to set a default path.
        username = getpass.getuser()
        default_path = fr"C:\Users\{username}\AppData\Local\NVIDIA Corporation\NVIDIA app\NvBackend\ApplicationStorage.json"
        self.path_edit.setText(default_path)
        path_layout.addWidget(self.path_edit)
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_file)
        path_layout.addWidget(self.browse_button)
        layout.addLayout(path_layout)
        
        # Checkbox to optionally set the file to read-only after modifications.
        self.readonly_checkbox = QtWidgets.QCheckBox("Set file as read-only after modifications")
        self.readonly_checkbox.setChecked(True)
        layout.addWidget(self.readonly_checkbox)
        
        # Layout for process and revert action buttons.
        btn_layout = QtWidgets.QHBoxLayout()
        self.process_button = QtWidgets.QPushButton("Process")
        self.process_button.clicked.connect(self.process_file)
        btn_layout.addWidget(self.process_button)
        self.revert_button = QtWidgets.QPushButton("Revert")
        self.revert_button.clicked.connect(self.revert_file)
        btn_layout.addWidget(self.revert_button)
        layout.addLayout(btn_layout)
        
        # Text area for logging application messages.
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def apply_dark_theme(self):
        """
        Applies a dark theme stylesheet to the entire application.
        """
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

    def log(self, message):
        """
        Appends a log message to the log text area.
        
        Args:
            message (str): The message to be logged.
        """
        self.log_text.append(message)

    def browse_file(self):
        """
        Opens a file dialog for selecting a JSON file.
        Updates the path input with the chosen file path.
        """
        current_path = self.path_edit.text().strip()
        initial_dir = os.path.dirname(current_path) if os.path.exists(current_path) else ""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select ApplicationStorage.json file",
            initial_dir,
            "JSON Files (*.json);;All Files (*)"
        )
        if file_path:
            self.path_edit.setText(file_path)

    def process_file(self):
        """
        Processes the JSON file to update override flags:
          - Validates file existence.
          - Confirms user intention.
          - Invokes modify_file to update keys.
          - Optionally sets the file to read-only.
        """
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm",
            f"Are you sure you want to modify this file?\n{file_path}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
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

    def revert_file(self):
        """
        Reverts the JSON file to its backup version:
          - Validates file existence.
          - Confirms user action.
          - Invokes revert_file to restore the backup.
        """
        file_path = self.path_edit.text().strip()
        if not os.path.exists(file_path):
            QtWidgets.QMessageBox.critical(self, "Error", f"File not found:\n{file_path}")
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Revert",
            f"Are you sure you want to revert changes to this file?\n{file_path}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            self.log("Revert cancelled by user.")
            return
        if revert_file(file_path, self.log):
            self.log("Revert successful.")
            # Toggle session flag based on whether modifications were processed.
            self.session_processed = not self.session_processed
        else:
            self.log("Revert failed or no valid backup available.")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """
        Overrides the default window close event.
        If modifications were made during the session, prompts the user to reboot.
        """
        if self.session_processed:
            reply = QtWidgets.QMessageBox.question(
                self,
                "Reboot Recommended",
                "Changes have been made that require a reboot to take effect.\nWould you like to reboot now?",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            )
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                os.system("shutdown /r /t 0")
        event.accept()

def main():
    """
    Entry point of the application.
      - Initializes the Qt application.
      - Creates and displays the main window.
      - Starts the event loop.
    """
    app = QtWidgets.QApplication(sys.argv)
    window = DLSSOverrideApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
