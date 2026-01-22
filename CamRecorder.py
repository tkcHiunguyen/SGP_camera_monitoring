import sys
import time
import tkinter
from tkinter import *
from tkinter import ttk
from tkinter.ttk import *
import os
import shutil, glob
from threading import *
import cv2
import datetime
import re
import imutils
import numpy as np
import win32com.client
import ctypes
from ping3 import ping
def Mbox(title, text, style):
    return ctypes.windll.user32.MessageBoxW(0, text, title, style)

from win32event import CreateMutex
from win32api import CloseHandle, GetLastError
from winerror import ERROR_ALREADY_EXISTS
class GetMutex:
    """ Limits application to single instance """
    def __init__(self):
        thisfile   = os.path.split(sys.argv[0])[-1]
        self.name  = thisfile + "_{D0E858DF-985E-4907-B7FB-8D732C3FC3B9}"
        self.mutex = CreateMutex(None, False, self.name)
        self.error = GetLastError()
    def IsRunning(self):
        return (self.error == ERROR_ALREADY_EXISTS)
    def __del__(self):
        if self.mutex: CloseHandle(self.mutex)
if (myapp := GetMutex()).IsRunning():
    sys.exit(0)

my_pid = os.getpid()
wmi = win32com.client.GetObject('winmgmts:')
all_procs = wmi.InstancesOf('Win32_Process')
proc_name = ''
for proc in all_procs:
   if proc.Properties_("ProcessID").Value == my_pid:
       proc_name = proc.Properties_("Name").Value
       break
if not proc_name in 'python.exe':
    for proc in all_procs:
       if proc.Properties_("Name").Value == proc_name:
            proc_pid = proc.Properties_("ProcessID").Value
            if proc_pid != my_pid:
                os.kill(proc_pid, 9)
                break

viewselect = None
root =  os.getcwd()

def savehistory(text):
    global root
    if not os.path.isdir(root + "/Files"):
        os.mkdir(root + "/Files")
    with open(root + '/Files/Log.txt', 'a') as f:
        a = str(datetime.datetime.today())
        f.write(a[:a.find('.')] + ' ' + text)
        f.write('\n')

def savecam(inf, save_del):
    global root
    lines = []
    if os.path.isfile(root + '/Files/Config.txt'):
        with open(root + '/Files/Config.txt', 'r') as f:
            for line in f:
                lines.append(line.replace('\n', ''))
    existing = False
    for i in range(len(lines)):
        if inf.split(' ')[0] == lines[i].split(' ')[0]:
            if save_del:
                lines[i] = inf
                existing = True
            else:
                lines.remove(lines[i])
            break
    if not existing and save_del:
        lines.append(inf)
    with open(root + '/Files/config.txt', 'w') as f:
        for l in lines:
            f.write(l)
            f.write('\n')

savehistory('ON')

window = Tk()
hourchanged = False
writeenable = True
run = True
fps = 5
daysrecord = 7
continous_record = 0
ip = '0.0.0.0'
port = 8083
codec = cv2.VideoWriter_fourcc(*"avc1")
scale = 0.5

treeview_selected = ''
view = "viewm"

def pingIP(ip):
    res = ping(ip)
    if res == False or res is None:
        return False
    else:
        return True

def isIP(address):
    parts = address.split(".")
    if len(parts) != 4:
        return False
    for item in parts:
        if not item.isdigit():
            return False
        if not 0 <= int(item) <= 255:
            return False
    return True

def close():
    global window, run
    if Mbox("Quit?", "Are you sure you want to quit?", 161) == 1:
        run = False
        window.configure(cursor='circle')
        window.quit()
    else:
        pass

datalogo = b'iVBORw0KGgoAAAANSUhEUgAAACEAAAAhCAYAAABX5MJvAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsQAAA7EAZUrDhsAAApcSURBVFhHjVdrjFxlGX7Omfucue5cdtvudna3pVtsuyUNBSwWA1JEQEOhmEBijJRI4i1NTEhIDIn88qeJiZEfYIg//GEUiQpeUCFKoGBbBEqR3S3ttuxcOjuzczszc64+7zddkEupXzJzzpzvm+99vvd93ud9j1ZtWD4uN9SKD5bJnabp6l7TNfi+D13X4XsePE9mR2s1TVPXy43Lg6ABdaFRPRBEMAhEooDrjT60rZ41V00EaDQSi8G1fYJxFSgZlwPzqSBkE18LQA/qSKV0NOsDnDp1Ai/94wW8eexljCWTCEQisC0byewYpma34MZb70AuPYZQJA7f9ZVPxFOfBuQSIEaPPOgI8PShMPDIQ0fw2rGjyKUyakPHddEzTQw8BwFPQzIWRyKdQG7DOCY3TeKe+76Osdw4NARBLPC4/lJALglCAGh6EJEQ8OB9d6Pb7yFmJLFar9FDPp+H4DoOhpYFyxrQGHj6MGLBMIx0Ejvmd+PWgwcxNzfP3UL0isc1NPUJQEbs+p/hErEgl5FNA9++/6vo9NoIhyOwhn2MZbMKohg3lXGHHBAwNuprTax2miiXV/D6sX/huT/+YRQK/sMP0DgByO+Pjo+BEJZrcOnaIJ547Am8ffKk4uZqvY7m2hrqFy4gqAcIrIu+2Ue7YyJEA1PZFDYmknCGLoYDC81mE21+mC/k1WhvXxNA68H+YHwoHGLMdXwEQjpMnuju226gBwxESb4BT97ttrkmSObbakPGBdloFLumN+Az05txgUZfXHgPXkCH3R8iX8zhZ7/8DbMnxt3FC8wWhpJ5poCtB+Z9T3hE4HoWJ4c0HGQGPE9CRtWJa/ULaDcaCJEDUb+PDIl6RTaOr8zP4chdB/DgXV/CDVfvxkw+DSMUQJAZ5Tg2Kivn8M5/3iYIckKMMBw6vSj36wBkvO8Jyx4SEcnDhREa/8a9d2J5eRkBzmaCDiaTCeyYnUKCWRCLRlAoZJAnP2LxOAlMrSApl88s41d/exWn17oweya6wx6efOoZlErbyBub1kYeULSnR9c5etETMuOqeOicqVXO4OzpJXTNHuyhic/NbsKBvXPYVspjejyNyZyBGAk57K2hvVrDoNOCO+ijkE1gOp+gaPkwCC7Gw9iOxX0JAAwhrxpDqSsRk2ejoUAouWW8FHNJzOr5CtyhLeFDPBpCMRVBYDjEoNmCZXaZJTYsx+Xpo8jmxmAkEsJ/RHj9/DU7MJ2OI8AQhJhRgYhBDnFvMSwqysP6vsMzM/QKDE2KXcseKC849JVNAs7vvYZ5fhU8utCjEEFOwz/E4jFk8gUUiwVoTGW720KnsUqdYMq6BjkVQaYwgQfuPICoZqM0UcCUeZbwxO/ibRqjXdEZufU9k1/KEyNpVazVBC035Em///AjiIdjGAxFCzQKUIo1w0C71sTiW2/CpydWyIHn/vkqfv7UszjxxnF0GJb6agX58TxuIVGvn5tE+fiL0ElW8bLYuWhNcU+AyBMVDocuEqzKbZyxbQtbdl6JA7fcygV0czSItytreGmpimdPvIGTNH5uYQlrzTZatTK6nQb+fuwEXjn6MpU0zoiGcdP+65AT3nQ6I+Mj2yMw/Ixsydld0SYdzDi1UGRKrpxWcT906B7EKM9h5nm414HdOI8K83+lTS90uti+ex4IJzBBobp5+zT2X38dZmbmmJKU73gEk6UrUD+7QqIyRdc595EhvNCWV5oUCFcZFrfL1ad/IgzF6T/9Fo//+Ee4/ca9uFCto9fpk3BBVswMw9HDzayY7y6eUuEbZ9FKsnpqzAzTbCvvRpOspqkJxPfczGQg7xgC8fj6EFAhHlJbOlPzSWQeX4erZHW0UL6jiRSePHwQs3ObUMxn2CskyZEh3N4A7XYD+276IlZrVZw89irGNxQILqsMuSRy3xkiaaSQmd8PbfNOxpx8+zACJQcuM0Y3mXJqCCnpLU25jDFjGllWD/sPfw8t1o0Wa4bO08XZW1TOn0PCSGPpzdepPz42TE7h6PMvYvH4a6gsLKg6I6puDXoYBtgBqfiLDokNTvCqyjo/Zq8P7a2Fc74RD6s5ASFjncFyiaXzePoHD8Do1ZFhE9Nl0SpX6pRlFwPuq7HWb9u+HRGGsHz+NLJj1A2qayaXhscaNH3oYeX29zfnEPv85lXHoN8XnRj5SHJXkNg8gvqT/OYfbXFrLo8+Q3Ch0USr20M6l0N6Uwn5mRnMbN2K8RkWr4EJh3VBWjxdcxAMhxCIU9aNBB1BgVK7iQnZf3RljJQZPZFI04CpUsYSBvOpR2b6/LgE6Fp9XPmFg+gO2hgyM0TtlsrvobxSwcIbp7B46l288tdXENfiMFhTwgl2UnoEmjGGaCqPPNU2Gg7AY/FT1i8CkdHvWzAYVt0wDHZNZC67ZpYUBJUHKOOMtU5QHplf2LkHpWtvZwnocYWP6UJR1YkrNk9gqpDATCmN8aKB4sQGAmdLSHHSWEl9kl3GRDHPUBrwqcauKyo8AtEjHwx6iuHwqPFxTjA9OSf6pQmRJG3FdQyPRSXcc/gIjMkr2XAw21jU4hEf6UwcEW4eZxakyIU0jUkGheMGnMEA4WRmtCe/stSSydJGTOSzSFL+pY4EA8JFVlQJw6aNU2iyXxhJqehEQCH1+ZvTRE8pYam/9rs/hBdN0WthppaOaDyKsUIaWtBlJ16lNjAjuJ6FXXVVM3tuY4aMOCYFUvgSZROUz6XYKAXpuUlFA+UvIU4uP67qhMpl5S7e8CIMlkcOe8g0C9e+r32H5OWzkIF6w8Ti4goWlspYrrZQO1fjeh+NShlT+w4hlKFHGE7fXd+LGcF7z7TRG8pBxY4qYLwl0kwmS6UbKqXz2BkLd+QqVVUannQqDnORusBO+sD9DzO1TKUpsVAQfMNggDsw2000WVfcdAkzV3+W7QC9aHO/i4cSO1pIwzvLZSSSaf5WbhuBkOGQvVu2bMNqdZWI5eRDxgwoFlLYOknCVatYPnuafeMEMptL2PvlB9H3glhj1bS6aySXg36zgaWGhTu+9Sh7TB6CfYvJHkSEStRRPLG4dJbvJpPkCcl1cXz8vYOuLp9bxO5dc+qnb3uovbeC84snEeV7R25jiX1EDwMWMZfacOz5P2Px6DNIRCxUGf8jP/kdkpmiauM8/rfXqiE3OcYOXcO/T76FTVt3EtDIpHgmyKb4E19+5J2zUTmP6YlxVtMeymeW0GqtYnbbVbDpQosFymwO2OonESXr19pd/OXXj+Pebz6EhLT9sqMoNNPcd/rg6ynO1Or0wBRDTL24OD4VhAzpittrDbg8icaXH52sjqXSCIfY6PB3u97hiTej0azisXvuQMnIojqzAY/+/hlobJiEzVyKleUKnFiQ6TxGAB+EQMZlQchQKSvhObMI3TaRYo8QBIWINWHQ8/muuRmHd23BtaEoirEMqo0Kjm+bwBMvvIx6vQmT1XQsX1R8EIMfHf8XiPWhB0QBdbRba3D6HXiUcmfoob3SwtO/+Cmi757F/AS5MjuDxI37MLtjFwrFcZJPsuzS249A6PgvIsB24Hfxu70AAAAASUVORK5CYII='
window.iconphoto(True, PhotoImage(data=datalogo))
window.title("CAMERA RECORDER")
window.geometry('640x360')
window.configure(background='#DCDAD5')
window.protocol("WM_DELETE_WINDOW", close)
window.resizable(False, False)
window.attributes("-alpha", 1)
window.attributes("-topmost", True)

mainframe = np.reshape(np.arange(0, 6220800, 1, np.uint8)*0+97, (1080, 1920, 3))
color = (255, 250, 255)
cv2.line(mainframe, (0, 720), (1920, 720), color=color, thickness=1)
cv2.line(mainframe, (1280, 360), (1920, 360), color=color, thickness=1)
cv2.line(mainframe, (640, 720), (640, 1080), color=color, thickness=1)
cv2.line(mainframe, (1280, 0), (1280, 1080), color=color, thickness=1)
bigframe = np.reshape(np.arange(0, 2764800, 1, np.uint8)*0+97, (720, 1280, 3))
smallframe = np.reshape(np.arange(0, 691200, 1, np.uint8)*0+97, (360, 640, 3))

frame = Frame(window)
frame.pack()

frame1 = Frame(window)
frame1.pack(pady=10)

frame2 = Frame(window)
frame2.pack()

style = ttk.Style()
style.theme_use('clam')
style.configure('Treeview.Heading', background="lemonchiffon1")
style.configure('Treeview', background='#717171', fieldbackground='#616161')

# scrollbar
scroll = Scrollbar(frame)
scroll.pack(side=RIGHT, fill=Y)
treeview = Treeview(frame, yscrollcommand=scroll.set, height=12)
treeview.pack()
scroll.config(command=treeview.yview)

treeview['columns'] = ("No.", 'CamName', 'IP', 'Status', 'Mode')
treeview.column("#0", width=0, stretch=NO)
treeview.column("No.", anchor=CENTER, width=50)
treeview.column("CamName", anchor=W, width=225)
treeview.column("IP", anchor=CENTER, width=200)
treeview.column("Status", anchor=CENTER, width=60)
treeview.column("Mode", anchor=CENTER, width=100)

treeview.heading("#0", text="", anchor=CENTER)
treeview.heading("No.", text="No.", anchor=CENTER)
treeview.heading("CamName", text="Camera Name", anchor=CENTER)
treeview.heading("IP", text="IP", anchor=CENTER)
treeview.heading("Status", text="Status", anchor=CENTER)
treeview.heading("Mode", text="Rec.Mode", anchor=CENTER)
treeview.tag_configure('even_Online', background='gray', foreground='green1')
treeview.tag_configure('even_Offline', background='gray', foreground='black')
treeview.tag_configure('odd_Online', foreground='green1')
treeview.tag_configure('odd_Offline', foreground='black')

# labels
Label(frame1, text="Cam Name").grid(row=0, column=0)
Label(frame1, text="IP").grid(row=0, column=1)
Label(frame1, text="Port").grid(row=0, column=2)
Label(frame1, text="User").grid(row=0, column=3)
Label(frame1, text="Password").grid(row=0, column=4)

def new(e):
    Save_button.config(state=NORMAL)

CamName = Entry(frame1, width=15, justify='center')
CamName.grid(row=1, column=0)
CamName.bind("<Button-1>", new)
CamName.insert(0, 'MWorkShop')

CamIp = Entry(frame1, width=13, justify='center')
CamIp.grid(row=1, column=1)
CamIp.bind("<Button-1>", new)
CamIp.insert(0, '192.168.20.8')

CamPort = Entry(frame1, width=7, justify='center')
CamPort.grid(row=1, column=2)
CamPort.bind("<Button-1>", new)
CamPort.insert(0, '554')

CamUser = Entry(frame1, width=10, justify='center')
CamUser.grid(row=1, column=3)
CamUser.bind("<Button-1>", new)
CamUser.insert(0, 'admin')

CamPass = Entry(frame1, width=10, justify='center', show="*")
CamPass.grid(row=1, column=4)
CamPass.bind("<Button-1>", new)
CamPass.insert(0, 'Automation@')

diskfull = False

def on_new_camera(line_treeview, Camera_name, Camera_ip, port, user, password):
    global hourchanged, run, cycle, fps, viewlist, mainframe, root, diskfull
    out = None
    frameold = None
    framefilter = None
    dir = root + "/Files/Videos/" + Camera_name
    dir_m = ''
    url = 'rtsp://' + str(user) + ':' + str(password) + '@' + str(Camera_ip) + ':' + str(port) + '/profile2/media.smp'
    camdata = None
    counter = 0
    hourchanged_old = hourchanged
    while run:
        try:
            cap = cv2.VideoCapture(url)
            fps_cam = min(25, int(cap.get(cv2.CAP_PROP_FPS)))
            seekframe = int(fps_cam / fps)
            globals()[Camera_name][7], frame = cap.read()
            scale = frame.shape[1] / 400
            if globals()[Camera_name][7]:
                for ct in range(int(fps_cam*2)):
                    cap.grab()
                v = treeview.item(line_treeview, 'value')
                if treeview_selected != '' and int(line_treeview) == int(treeview_selected):
                    style.map('Treeview', foreground=[('selected', 'green1')])
                if line_treeview % 2 == 0:
                    treeview.item(line_treeview, values=(v[0], v[1], v[2], "Online", v[4]), tags="even_Online")
                else:
                    treeview.item(line_treeview, values=(v[0], v[1], v[2], "Online", v[4]), tags="odd_Online")
                menus.add_command(label=Camera_name, command=cmd)
                while run:
                    lost = False
                    for ct in range(seekframe):
                        if not cap.grab():
                            lost = True
                            break
                    globals()[Camera_name][7], globals()[Camera_name][6] = cap.retrieve()
                    camdata = globals()[Camera_name]
                    if Camera_name not in globals() or not camdata[7] or lost:  # Deleted or lost comm
                        cap.release()
                        break
                    else:
                        frame = globals()[Camera_name][6]

                        if hourchanged != hourchanged_old or out is None:
                            hourchanged_old = hourchanged
                            if out is None:
                                pass
                            else:
                                if out.isOpened():
                                    out.release()
                            if not os.path.isdir(root + "/Files"):
                                os.mkdir(root + "/Files")
                            if not os.path.isdir(root + "/Files/Videos"):
                                os.mkdir(root + "/Files/Videos")
                            if not os.path.isdir(dir):
                                os.mkdir(dir)
                            dir_y = dir + "/" + str(datetime.datetime.now().year)
                            if not os.path.isdir(dir_y):
                                os.mkdir(dir_y)
                            dir_m = dir_y + "/" + str(datetime.datetime.now().month)
                            if not os.path.isdir(dir_m):
                                os.mkdir(dir_m)
                            filename = dir_m + '/' + Camera_name + ' {0}h.mp4'.format(
                                datetime.datetime.now().strftime("%d-%m-%Y %H"))
                            h, w, c = frame.shape
                            if os.path.isfile(filename):
                                filename = dir_m + '/' + Camera_name + ' {0}.mp4'.format(
                                    datetime.datetime.now().strftime("%d-%m-%Y %Hh%Mm%Ss"))
                            out = cv2.VideoWriter(filename, codec, fps, (w, h))
                            checkfilelist(dir)

                        if writeenable:
                            if camdata[1] == 'Motion':
                                motion, frameold, frame, framefilter, counter = motiondetect_for_cam(frame, frameold, scale, dir_m, Camera_name, framefilter, counter)
                                if motion:
                                    out.write(frame)
                            else:
                                out.write(frame)
                        elif not diskfull:
                            diskfull = True
                            statusbar.itemconfigure(statustext, text="Disk full")

                        try:
                            if camdata[8] is not None:
                                w = 640
                                if camdata[8] == "viewmain":
                                    w = 1280
                                    mainframe[0:720, 0:1280] = imutils.resize(frame, width=w)
                                elif camdata[8] == "view2":
                                    mainframe[720:1080, 0:640] = imutils.resize(frame, width=w)
                                elif camdata[8] == "view3":
                                    mainframe[720:1080, 640:1280] = imutils.resize(frame, width=w)
                                elif camdata[8] == "view4":
                                    mainframe[0:360, 1280:1920] = imutils.resize(frame, width=w)
                                elif camdata[8] == "view5":
                                    mainframe[360:720, 1280:1920] = imutils.resize(frame, width=w)
                                elif camdata[8] == "view6":
                                    mainframe[720:1080, 1280:1920] = imutils.resize(frame, width=w)
                        except Exception as err:
                            pass
                            #print("...............", err)

                if Camera_name not in globals():
                    delcam_in_menu(Camera_name)
                    cap.release()
                    for v in viewlist:
                        if Camera_name == v[0]:
                            viewlist.remove(v)
                    if camdata is not None:
                        clear_view(camdata[8])
                    if not (out is None):
                        if out.isOpened():
                            out.release()
                    break
                camdata = globals()[Camera_name]
                if treeview_selected != '' and int(line_treeview) == int(treeview_selected): style.map('Treeview', foreground=[
                    ('selected', 'black')])
                if line_treeview % 2 == 0:
                    treeview.item(line_treeview, values=(camdata[5], Camera_name, Camera_ip, "Offline", camdata[1]),
                                  tags="even_Offline")
                else:
                    treeview.item(line_treeview, values=(camdata[5], Camera_name, Camera_ip, "Offline", camdata[1]),
                                  tags="odd_Offline")
                if camdata[8] is not None:
                    clear_view(camdata[8])
                delcam_in_menu(Camera_name)
                for v in viewlist:
                    if Camera_name == v[0]:
                        viewlist.remove(v)

                cap.release()
                if not (out is None):
                    if out.isOpened():
                        out.release()
        except:
            if Camera_name not in globals():
                cap.release()
                delcam_in_menu(Camera_name)
                for v in viewlist:
                    if Camera_name == v[0]:
                        viewlist.remove(v)
                if camdata is not None:
                    clear_view(camdata[8])
                break
            pass
        time.sleep(1)

def newcam():
    camera_name = 'Camera ' + CamName.get()
    line_name = CamName.get()
    ip_addr = CamIp.get()
    port = CamPort.get()
    user = CamUser.get()
    password = CamPass.get()
    condi = camera_name not in globals() and line_name != '' and isIP(
        ip_addr) and port.isdigit() and user != '' and password != '' and pingIP(ip_addr)
    if condi:
        line_treeview = 1
        if len(treeview.get_children())>0:
            for m in treeview.get_children():
                if int(m) > line_treeview:
                    line_treeview = int(m)
            line_treeview = line_treeview + 1
        index = len(treeview.get_children()) + 1
        globals()['Camera ' + CamName.get()] = [False, 'Continuous', CamUser.get(), CamPass.get(), CamPort.get(), index, frame, False, None]
        if line_treeview % 2 == 0:
            treeview.insert(parent='', index='end', iid=str(line_treeview), text='',
                            values=(index, 'Camera '+CamName.get(), CamIp.get(), "Offline", 'Continuous'), tags="even_Offline")
        else:
            treeview.insert(parent='', index='end', iid=str(line_treeview), text='',
                            values=(index, 'Camera '+CamName.get(), CamIp.get(), "Offline", 'Continuous'), tags="odd_Offline")
        savecam(line_name + ' ' + ip_addr + ' ' + port + ' ' + user + ' ' + password, True)
        Thread(target=on_new_camera, args=(line_treeview, camera_name, ip_addr, port, user, password, )).start()
        statusbar.itemconfigure(statustext, text='New record for Camera ' + CamName.get())
    else:
        statusbar.itemconfigure(statustext, text="Camera invalid or offline")
        pass

def del_record():
    global counter, treeview_selected
    selected = treeview.focus()
    v=treeview.item(selected, 'value')
    if v[1] in globals():
        del globals()[v[1]]
        savecam(str(v[1]).replace("Camera ", ''), False)
    treeview.delete(selected)
    Del_button.config(state=DISABLED)
    index = 1
    for line in treeview.get_children():
        v = treeview.item(line, 'value')
        if index  % 2 == 0:
            treeview.item(line, values=(index, v[1], v[2], v[3], v[4]), tags='even_' + v[3])
        else:
            treeview.item(line, values=(index, v[1], v[2], v[3], v[4]), tags='odd_' + v[3])
        try:
            globals()[v[1]][5] = index
        except:
            pass
        index = index + 1
    treeview_selected = ''

Save_button = Button(frame1, text="New", command=newcam, state = DISABLED, width=6)
Save_button.grid(row=1, column=5, padx=5)

Del_button = Button(frame1, text="Delete", command=del_record, state = DISABLED, width=6)
Del_button.grid(row=1, column=6, padx=1)

statusbar = Canvas(frame2, height = 12, width = 600, background='silver', relief='sunken', border=True)
statusbar.pack()
statusprogress = statusbar.create_rectangle(0, 0, 0, 0, fill='green')
statustext = statusbar.create_text(5, 10, text='', anchor='w')

def newcamfromfile(data):
    global statusbar
    camera_name = 'Camera ' + data[0]
    line_name = data[0]
    ip_addr = data[1]
    port = data[2]
    user = data[3]
    password = data[4]
    condi = camera_name not in globals() and line_name != '' and isIP(ip_addr) and port.isdigit() and user != '' and password != ''
    if condi:
        line_treeview = 1
        if len(treeview.get_children())>0:
            for m in treeview.get_children():
                if int(m) > line_treeview:
                    line_treeview = int(m)
            line_treeview = line_treeview + 1
        index = len(treeview.get_children()) + 1
        globals()[camera_name] = [False, 'Continuous', user, password, port, index, frame, False, None]
        if line_treeview % 2 == 0:
            treeview.insert(parent='', index='end', iid=str(line_treeview), text='',
                            values=(index, camera_name, ip_addr, "Offline", 'Continuous'), tags="even_Offline")
        else:
            treeview.insert(parent='', index='end', iid=str(line_treeview), text='',
                            values=(index, camera_name, ip_addr, "Offline", 'Continuous'), tags="odd_Offline")
        Thread(target=on_new_camera, args=(line_treeview, camera_name, ip_addr, port, user, password, )).start()
        statusbar.itemconfigure(statustext, text='New record for ' + camera_name)
    else:
        statusbar.itemconfigure(statustext, text="Camera invalid or offline")
        pass

if os.path.isfile('Files/Config.txt'):
    with open('Files/Config.txt', 'r') as f:
        for line in f:
            data = line.replace('\n', '').split(' ')
            if len(data) >= 2:
                if "fps" in data[1] and data[0].isdigit(): fps = max(1, min(20, int(data[0])))
                elif 'days' in data[1] and data[0].isdigit(): daysrecord = max(1, int(data[0]))
                elif len(data) == 5:
                    newcamfromfile(data)
cycle = 1 / fps

def motiondetect_for_cam(frame, frameold, scale, dir_m, Camera_name, framefilter, counter):
    count = counter

    fr = imutils.resize(frame, width=400)
    #Đổi màu
    #fr = cv2.cvtColor(fr, cv2.COLOR_RGB2HSV)
    #cv2.imshow("1 Doi mau", fr)

    #Chuyển xám..................................
    gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
    graynew = np.multiply(gray, 0.01)
    if framefilter is None:
        grayold = np.multiply(gray, 0.99)
    else:
        grayold = np.multiply(framefilter, 0.99)
    framefilter = np.add(grayold, graynew)

    #Làm mờ......................................
    graysmooth = cv2.bilateralFilter(gray, 5, 75, 10)
    #cv2.imshow("3 Xam2", gray)
    if frameold is None: frameold=graysmooth

    #Trừ ảnh.....................................
    frameDelta = cv2.absdiff(frameold, graysmooth)

    #Ngưỡng......................................
    thresh = cv2.threshold(frameDelta, 50, 255, cv2.THRESH_BINARY)[1]
    #cv2.imshow("5 thresh", thresh)

    # Phép giãn nỡ...............................
    thresh = cv2.dilate(thresh, None, iterations=2)
    #cv2.imshow("6 Gian no", thresh)

    # Phép giãn co..............................
    #thresh = cv2.erode(thresh, None, iterations=2)
    contours, hierarchy = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        # Ignore small contours
        #print(cv2.contourArea(contour))
        area = cv2.contourArea(contour)
        if area < 500:
            continue
        #print(cv2.contourArea(contour))
        if count == 0:
            x, y, w, h = cv2.boundingRect(contour)
            if h/w > 1.5 or area > 5000:
                if not os.path.isdir(dir_m + "/Pictures"):
                    os.mkdir(dir_m + "/Pictures")
                filename = dir_m + '/Pictures/' + Camera_name + ' {0}.jpg'.format(
                    datetime.datetime.now().strftime("%d-%m-%Y %Hh%Mm%Ss"))
                x = int(x * scale)
                y = int(y * scale)
                w = int(w * scale)
                h = int(h * scale)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 1)
                cv2.imwrite(filename, frame)
                count = 1
    if count > 0:
        count += 1
        if count > 25:
            count = 0
    if len(contours) > 0:
        return [True, graysmooth, frame, framefilter, count]
    else:
        return [False, graysmooth, frame, framefilter, count]

def condition():
    global hourchanged, writeenable, run, diskfull
    h = datetime.datetime.now().hour
    while run:
       if h != datetime.datetime.now().hour:
            hourchanged = not hourchanged
            h = datetime.datetime.now().hour
       if (shutil.disk_usage("/").free // (2 ** 30)) > 5:
           writeenable = True
           diskfull = False
       else:
           writeenable = False
       time.sleep(2)
Thread(target=condition).start()

#Kiểm tra xóa file video cũ
def checkfilelist(dir):
    global daysrecord
    if os.path.isdir(dir):
        obj_list = glob.glob(dir + "/**", recursive=True)
        for obj in obj_list:
            filefull = obj.replace("\\", '/')
            filename = os.path.basename(filefull)
            if ".avi" in filename or ".mp4" in filename:
                try:
                    date = re.search(r'\d{2}-\d{2}-\d{4}', filename).group()
                    d = datetime.datetime.strptime(date, '%d-%m-%Y')
                    if int((datetime.datetime.now() - d).days) > daysrecord:
                        os.remove(filefull)
                except:
                    pass

lineold = '-1'
def clicker(e):
    global lineold, treeview_selected
    if lineold in globals():
        if e.x < 540:
            globals()[lineold][0] = False
    if len(treeview.get_children()) != 0:
        treeview_selected = treeview.identify_row(e.y)
        if treeview_selected != '':
            v = treeview.item(treeview_selected, 'value')
            line = v[1]
            if v[3] == 'Online':
                if e.x > 540:
                    if v[4] == 'Continuous':
                        treeview.item(treeview_selected, values=(v[0], v[1], v[2], v[3], 'Motion'))
                        globals()[line][1] = 'Motion'
                    else:
                        treeview.item(treeview_selected, values=(v[0], v[1], v[2], v[3], 'Continuous'))
                        globals()[line][1] = 'Continuous'
                if e.x < 540:
                    globals()[line][0] = True
                    lineold = line
            if v[3] == 'Online':
                style.map('Treeview', foreground=[('selected', 'green1')])
            else:
                style.map('Treeview', foreground=[('selected', 'black')])
        else:
            treeview.selection_remove(treeview.selection())
            Del_button.config(state=DISABLED)
            if str(lineold) not in '-1':
                globals()[lineold][0] = False
            lineold = '-1'
treeview.bind("<Button-1>", clicker)

def Dclicker(e):
    global treeview_selected, remote_desktop
    if len(treeview.get_children()) != 0:
        treeview_selected = treeview.identify_row(e.y)
        if treeview_selected != '':
            Del_button.config(state=NORMAL)
        else:
            Del_button.config(state=DISABLED)
treeview.bind("<Double-1>", Dclicker)

def new(url):
    condi = ('Camera ' + CamName.get()) not in globals() and CamName.get() != '' and isIP(CamIp.get()) and CamPort.get().isdigit() and CamUser.get() != '' and CamPass.get() != '' and pingIP(CamIp.get())
    if condi:
        counter = 1
        if len(treeview.get_children())>0:
            for m in treeview.get_children():
                if int(m) > counter:
                    counter = int(m)
            counter = counter + 1
        index =  len(treeview.get_children()) + 1
        globals()['Camera ' + CamName.get()] = [False, 'Continuous', CamUser.get(), CamPass.get(), CamPort.get(), index, frame, False, None]
        if counter % 2 == 0:
            treeview.insert(parent='', index='end', iid=str(counter), text='',
                            values=(index, 'Camera '+CamName.get(), CamIp.get(), "Offline", 'Continuous'), tags="even_Offline")
        else:
            treeview.insert(parent='', index='end', iid=str(counter), text='',
                            values=(index, 'Camera '+CamName.get(), CamIp.get(), "Offline", 'Continuous'), tags="odd_Offline")
        v = treeview.item(str(counter), 'value')
        Thread(target=on_new_camera, args=(counter, v[1], v[2], CamPort.get(), globals()[v[1]][2], globals()[v[1]][3], )).start()
        statusbar.itemconfigure(statustext, text='New record for Camera ' + CamName.get())
    else:
        statusbar.itemconfigure(statustext, text="Camera invalid or offline")
        pass
        #print("Cam invalid or cam not online")

window.bind("<Escape>", lambda event: window.attributes("-fullscreen", False))

class MyMenu(tkinter.Menu):
    def add_command(self, **kwargs):
        callback = kwargs.pop('command', None)
        text = kwargs.get('label')
        super().add_command(**kwargs, command=(lambda: callback(text)) if callback else None)
    def add_separator(self, **kwargs):
        super().add_separator(**kwargs)

def clear_view(view):
    global mainframe
    if view == "viewmain":
        mainframe[0:720, 0:1280] = bigframe
    elif view == "view2":
        mainframe[720:1080, 0:640] = smallframe
    elif view == "view3":
        mainframe[720:1080, 640:1280] = smallframe
    elif view == "view4":
        mainframe[0:360, 1280:1920] = smallframe
    elif view == "view5":
        mainframe[360:720, 1280:1920] = smallframe
    elif view == "view6":
        mainframe[720:1080, 1280:1920] = smallframe

viewlist = []
def cmd(camname):
    global viewselect, camold, view
    if camname == 'Setting':
        window.deiconify()
    else:
        for v in viewlist:
            if viewselect == v[1]:
                globals()[v[0]][8] = None
                v[1] = None
        if globals()[camname][8] is not None:
            clear_view(globals()[camname][8])
        globals()[camname][8] = viewselect
        exist = False
        for v in viewlist:
            if camname in v[0]:
                v[1] = viewselect
                exist = True
                break
        if not exist:
            viewlist.append([camname, viewselect])
        color = (255, 250, 255)
        cv2.line(mainframe, (0, 720), (1920, 720), color=color, thickness=1)
        cv2.line(mainframe, (1280, 360), (1920, 360), color=color, thickness=1)
        cv2.line(mainframe, (640, 720), (640, 1080), color=color, thickness=1)
        cv2.line(mainframe, (1280, 0), (1280, 1080), color=color, thickness=1)

def delcam_in_menu(camname):
    if camname in globals():
        globals()[camname][8] = None
    for i in range(menus.index("end")+1):
        try:
            if menus.entrycget(i, "label") == camname:
                menus.delete(i)
        except:
            pass

menus = MyMenu(window, tearoff=0)
menus.add_command(label="Setting", command=cmd)
menus.add_separator()

def do_popup(event, x, y, flags, param):
    global viewselect
    if event == 5:
        try:
            if x in range(1280):
                if y in range(720):
                    viewselect = 'viewmain'
                elif x in range(640):
                    viewselect = 'view2'
                else:
                    viewselect = 'view3'
            else:
                if y in range(360):
                    viewselect = 'view4'
                elif y in range(360, 720):
                    viewselect = 'view5'
                else:
                    viewselect = 'view6'
            menus.tk_popup(x + cv2.getWindowImageRect('view')[0], y + cv2.getWindowImageRect('view')[1])
        finally:
            menus.grab_release()
    elif event == 1:
        window.withdraw()

def update():
    global cycle, mainframe, viewselect, run
    prev = 0
    cv2.namedWindow("view", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("view", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    while run:
        remain = max(0.0, (cycle - (time.time() - prev)))
        time.sleep(remain)
        prev = time.time()
        cv2.imshow("view", mainframe)
        cv2.setMouseCallback("view", do_popup)
        k = cv2.waitKey(1) & 0xFF
        cv2.waitKeyEx(1)
        if k == 27:  # exit fullscreen
            #print("exit fullscreen")
            cv2.setWindowProperty("view", cv2.WND_PROP_AUTOSIZE, 1)
            cv2.destroyWindow("view")
        try:
            pos = cv2.getWindowImageRect('view')
            if pos[0] == 0 and pos[1] == 23:
                cv2.destroyWindow("view")
                cv2.setWindowProperty("view", cv2.WND_PROP_AUTOSIZE, 0)
                cv2.namedWindow("view", cv2.WND_PROP_FULLSCREEN)
                cv2.setWindowProperty("view", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        except:
            pass
    cv2.destroyWindow("view")
Thread(target=update).start()

window.mainloop()
savehistory('OFF')
