import hashlib
import os

def calculate_hash(filename):
    sha256 = hashlib.sha256()

    with open(filename, "rb") as file:
        while chunk := file.read(4096):
            sha256.update(chunk)

    return sha256.hexdigest()

banner = r"""
 _____ _ _        ___     _            _ _
|  ___(_) | ___  |_ _|_ _| |_ ___  __ _(_) |_ _   _
| |_  | | |/ _ \  | || '_ \ __/ _ \/ _` | | __| | | |
|  _| | | |  __/  | || | | ||  __/ (_| | | |_| |_| |
|_|   |_|_|\___| |___|_| |_|\__\___|\__, |_|\__|\__, |
     ____ _               _        |___/       |___/
    / ___| |__   ___  ___| | _____ _ __
   | |   | '_ \ / _ \/ __| |/ / _ \ '__|
   | |___| | | |  __/ (__|   <  __/ |
    \____|_| |_|\___|\___|_|\_\___|_|
"""
print(banner)
print("GitHub: https://github.com/YOUR_USERNAME\n")

while True:
    print("\n--- File integrity checker ---")
    print("1. Create baseline")
    print("2. Check integrity")
    print("3. Exit")

    choice = input("Enter your choice: ")

    if choice == "1":
        filename = input("Enter the filename: ")
        file_hash = calculate_hash(filename)

        with open("baseline.txt", "w") as file:
            file.write(file_hash)

        print("Baseline created successfully!")

    elif choice == "2":
        filename = input("Enter the file name: ")

        if not os.path.exists("baseline.txt"):
            print("No baseline found. Create one first.")
            continue

        current_hash = calculate_hash(filename)

        with open("baseline.txt", "r") as file:
            original_hash = file.read()

        if current_hash == original_hash:
            print("file is unchanged.")
        else:
            print("file has been modified!")

    elif choice == "3":
        print("Exiting...")
        break

    else:
        print("invalid choice.")
