import datetime
import os
import re
import json
import copy
from math import floor
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db

# Initializing firebase realtime database
cred = credentials.Certificate('key.json')
fb_app = firebase_admin.initialize_app(cred, {
    'databaseURL': "https://itcs4155-b4b9e-default-rtdb.firebaseio.com/"
})


# Get the file from local storage
def get_file():
    current_dir = os.path.dirname(__file__)
    current_dir = os.path.join(current_dir, 'logs')
    if not os.path.exists(current_dir):
        os.mkdir(current_dir)
        in_folder = os.path.join(current_dir, 'in')
        out_folder = os.path.join(current_dir, 'out')
        os.mkdir(in_folder)
        os.mkdir(out_folder)
        print("Please place logs in the newly created logs/in folder, then re-enter.")
        exit()
    file_name = input("File Name (no extension): ") + ".log"
    file = os.path.join(current_dir, 'in', file_name)
    if os.path.exists(file):
        print("Log file exists, extracting...")
        return file
    else:
        print("File does not exist. Please try again.")
        return None


print("Welcome to the wifi log extraction script.")
print("Please enter the name of the log file you want to extract from (in logs/in folder)")

file_obj = None
while file_obj is None:
    file_obj = get_file()
log = open(file_obj, 'r')


# Cleans time chunk data up for final export
def chunk_cleanup(c_s, mins):
    # Generate name based on time chunk in minutes, then update current chunk by the step amount
    chunk_name = c_s.__str__() + "-" + (c_s + mins).__str__()
    c_s = c_s + mins
    # Tally up the total devices in the time chunk, then assign to the chunk list
    total_devices = 0
    for building in building_list['buildings']:
        total_devices += building_list['buildings'][building]['device_count']
        # Remove the mac list to drastically reduce the file size and clean it up
        building_list['buildings'][building].pop('mac_list')
        building_list['total_devices'] = total_devices
    return chunk_name, c_s


# Variables for chunk list
match_strings = ['Assoc success', 'Disassoc from sta']  # 'Auth', 'Deauth' (Different possible string matches)

date = ''
weekday = ''
start_time = datetime.datetime(1900, 1, 1, 0, 0)  # Initialize start time to 00:00:00
minutes = 30  # Number of minutes for each chunk
time_step = datetime.timedelta(minutes=minutes)
current_step = 0

building_list = {'total_devices': 0, 'buildings': {}}
chunk_list = {}
# End Variables

for line in log:
    # Only check lines for events we care about (assoc and disassoc)
    if any(s in line for s in match_strings):
        # Extract date from log only once per log
        if date == '':
            date = re.sub(' +', ' ', line[0:6])
            date = date + ' 2021'
            # Check to see if log already in database
            ref = db.reference('/historical/' + date)
            if ref.get() is not None:
                print("This log is already in the database. Process is complete.")
                exit()
            weekday = datetime.datetime.strptime(date, '%b %d %Y').strftime('%A')
            print("Log file date: " + weekday + ", " + date)

        # Extract time from line
        time = line[7:15]
        time = datetime.datetime.strptime(time, '%H:%M:%S')

        # Compare time to start time to establish if it is within the chunk or has exceeded
        time_delta = time - start_time
        if time_delta >= time_step:
            # Adds final touches to chunk then adds it to the list
            name, current_step = chunk_cleanup(current_step, minutes)
            chunk_list[name] = building_list

            # Reset the building list and start time to reflect a new time chunk forming
            building_list = {'total_devices': 0, 'buildings': {}}
            start_time = time

        # Extract mac address from line
        # Changes mac extraction based on line type (association or disassociation)
        if 'Assoc success' in line:
            mac = re.search('Assoc success @(.*): AP', line).group(1)
            mac = mac[18:]
        else:
            mac = re.search('Disassoc from sta: (.*): AP', line).group(1)

        # Extract AP name from line
        ap = re.search('AP (.+?)-AP', line)
        if ap:
            ap = ap.group(1)

            # Check for dashes and remove them to get raw AP name
            strip_index = ap.rfind('-')
            if strip_index != -1:
                ap = ap[(strip_index + 1):]

            # Updates these random AP names which don't follow standard formatting for some reason
            if ap in ['LF', 'RF']:
                ap = 'Phil'

            # Remove any extraneous numbers to get raw building names
            building = re.search("(^\D+)", ap).group(1)

            # Adds or updates building list
            if building in building_list['buildings']:
                if mac not in building_list['buildings'][building]['mac_list']:
                    building_list['buildings'][building]['device_count'] += 1
                    building_list['buildings'][building]['mac_list'].append(mac)
            else:
                building_list['buildings'][building] = {'device_count': 1, 'mac_list': [mac]}

# Add the final chunk not covered by the loop
name, current_step = chunk_cleanup(current_step, minutes)
chunk_list[name] = building_list

log.close()
print("Log file extracted, uploading to database...")

# Upload the historical data to the database
ref = db.reference('/historical/' + date)
ref.set(chunk_list)
print("Log file uploaded to database. Checking master file...")

# Try to get master-total for the specific weekday
ref = db.reference('/weekdays/' + weekday + '/master-total')
master = ref.get()

# Create/update master & average files for the weekday
if master is None:
    print("Empty master file for " + weekday + ". Creating one now...")
    ref.set(chunk_list)
    # Assigning initial count of 1 to each time chunk
    for chunk in chunk_list:
        ref = db.reference('/weekdays/' + weekday + '/master-total/' + chunk)
        ref.child('number').set(1)
    ref = db.reference('/weekdays/' + weekday + '/average')
    ref.set(chunk_list)
    print("Fresh master/average file created. Process is complete.")
else:
    print("Average file for " + weekday + " found, backing up and updating...")
    # Dump current master-total for backup in case something goes wrong
    with open('logs/out/master-total.json', 'w') as outfile:
        json.dump(master, outfile, indent=4)
    print("Dumped backup master file for " + weekday + ".")

    # Create copy of master for averaging
    average = copy.deepcopy(master)

    # Either update all building counts for each chunk or add a new entry if it didn't exist
    for chunk in chunk_list:
        master[chunk]['total_devices'] += chunk_list[chunk]['total_devices']
        master[chunk]['number'] += 1
        for building in chunk_list[chunk]['buildings']:
            if building in master[chunk]['buildings']:
                master[chunk]['buildings'][building]['device_count'] += chunk_list[chunk]['buildings'][building][
                    'device_count']
            else:
                master[chunk]['buildings'][building] = chunk_list[chunk]['buildings'][building]
                average[chunk]['buildings'][building] = master[chunk]['buildings'][building]

    # Average out all updated device counts
    for chunk in average:
        number = master[chunk]['number']
        average[chunk]['total_devices'] = floor(master[chunk]['total_devices'] / number)
        for building in average[chunk]['buildings']:
            average[chunk]['buildings'][building]['device_count'] = floor(
                master[chunk]['buildings'][building]['device_count'] / number)
        # Remove extraneous number entry after averaging each time chunk
        average[chunk].pop('number', None)

    # Update master-total in database
    ref.set(master)

    # Update weekday average in database
    ref = db.reference('/weekdays/' + weekday + '/average')
    ref.set(average)
    print("Master and average entries updated in database. Process is complete.")
