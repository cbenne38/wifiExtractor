import datetime
import os
import re
import json


def get_file():
    file_name = input("File Name: ")
    current_dir = os.path.dirname(__file__)
    file = os.path.join(current_dir, file_name)
    if os.path.exists(file):
        print("Log file exists, extracting...")
        return file
    else:
        print("File does not exist. Please try again.")
        exit()


print("Welcome to the wifi log extraction script.")
print("Please enter the name of the log file you want to extract from.")

log = open(get_file(), 'r')


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
            building = re.search('(^\D+)', ap).group(1)

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

# Dump chunk array to json for export (will be replaced by database)
with open(date + '.json', 'w') as outfile:
    json.dump(chunk_list, outfile, indent=4)

print("Log file has been processed and the data has been exported!")
