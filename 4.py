from protocols.ls_masterk import LSMasterKReader

conn = {
    "port": "COM8",
    "baudrate": 9600,
    "parity": "E",
    "bytesize": 8,
    "stopbits": 1,
    "timeout": 2,
    "station": "01"
}

plc = LSMasterKReader(conn)

plc.connect()

print("==== READ D100 ====")
plc.read_word("D100", 1)

print("==== READ M0 ====")
plc.read_word("M0", 1)

plc.close()