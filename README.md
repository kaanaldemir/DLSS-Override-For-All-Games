
# DLSS Override For All Games

This is a simple, open-source tool for the community. It provides a graphical interface for modifying NVIDIA's `ApplicationStorage.json` file so that DLSS can be overridden for games that are not officially whitelisted.

The tool works by searching through the JSON file for specific DLSS override keys and flipping their values from `true` to `false`. It also creates a backup of the file (with metadata) so that you can revert the changes if needed. Note that if the file is updated externally (for example, by driver update), the backup will be refreshed to prevent reverting to an obsolete version.

<p align="left">
  <a href="https://github.com/kaanaldemir/dlss-override-for-all-games/releases/latest/download/DLSS.Override%2B.exe" title="Download DLSS.Override+.exe" style="background-color:#ff4500; color:#fff; padding:25px 50px; font-size:28px; font-weight:bold; border-radius:12px; text-decoration:none; display:flex; align-items:center; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);">
    <img src="https://unpkg.com/@primer/octicons/build/svg/download-24.svg" alt="Download Icon" style="width:100px; filter: brightness(0) invert(1); margin-right:20px;">
    <span style="display:inline-block; text-align:center;">Download DLSS.Override+.exe</span>
  </a>
</p>

<script type="text/javascript" src="https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js" data-name="bmc-button" data-slug="kaanaldemir" data-color="#5F7FFF" data-emoji="👇" data-font="Poppins" data-text="Download Here" data-outline-color="#000000" data-font-color="#ffffff" data-coffee-color="#FFDD00"></script>

<a href="https://www.buymeacoffee.com/kaanaldemir" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 45px !important;width: 163px !important;">
</a>

## Features

- **Automatic file path detection:**  
  The tool automatically fills in the default path based on your current user account. You can adjust or browse for a different file if needed.

- **DLSS override updates:**  
  It scans the JSON file recursively to find and update the following keys:
  - `Disable_FG_Override`
  - `Disable_RR_Override`
  - `Disable_SR_Override`
  - `Disable_RR_Model_Override`
  - `Disable_SR_Model_Override`

- **Backup and revert:**  
  A backup is created (with accompanying metadata) so that you can revert to the original state, as long as the file has not been externally modified.

- **Read-only option:**  
  Optionally, the file can be set to read-only after modifications to prevent accidental changes.

- **Concise logging:**  
  The tool logs a summary of changes for each game in a clear, single-line format.

## Installation

### Prerequisites

- Python 3.x
- [PyQt6](https://pypi.org/project/PyQt6/)

### Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/kaanaldemir/dlss-override-for-all-games.git
   cd dlss-override-for-all-games
