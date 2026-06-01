import os
from pathlib import Path

def find_dir(root_path, target_name):
    print(f"Scanning {root_path} for '{target_name}'...")
    root = Path(root_path)
    for p in root.rglob(f"*{target_name}*"):
        try:
            if p.is_dir():
                print(f"FOUND: {p}")
        except Exception:
            pass

if __name__ == "__main__":
    # Scan Desktop and user folder (except AppData, .gemini, etc.)
    user_home = Path.home()
    for child in user_home.iterdir():
        if child.is_dir() and child.name not in ["AppData", ".gemini", ".cache", "NTUSER.DAT", "System Volume Information", "Local Settings", "Application Data"]:
            try:
                find_dir(child, "AI-Native-E-KYC")
                find_dir(child, "ekyc")
            except Exception as e:
                print(f"Error scanning {child}: {e}")
