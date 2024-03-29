import util
import ot
import os
import time
import sys
import circuit 
import json
import bobHandler as bh

os.system('clear')

class Alice:
    def __init__(self):
        self.server = util.ServerSocket()

    def waitForBob(self):
        payload = self.server.receive()
        if payload == "initiate":
            return True
        return False

    def obliviousTransfer(self, input1, input2):
        alice = ot.Alice(input1, input2)
        # wait until bob is online
        print("waiting to receive")
        ready = self.server.receive()
        if ready:
            # send c
            c = alice.send_c()
            self.server.send(c)
            # wait for bob to send H0 so that we can receive it.
            h0 = self.server.receive()
            # compute c_1, E, length
            c_1, E, length = alice.sendMessage(h0)
            # send c_1, E, length to Bob.
            payload = (c_1, E, length)
            self.server.send(payload)
            print("Completed transaction of payload.")

    def transferGarbledCircuit(self,garbled):
        self.server.send(garbled)

class Bob:
    def __init__(self):
        self.client = util.ClientSocket()
        self.inputs = []
        self.garbledTable = None

    def initiate(self):
        self.client.send("initiate")

    def obliviousTransfer(self, inputIndex):
        # set up ot class for Bob
        bob = ot.Bob(inputIndex)
        # set up ready.
        print("sending hello to allice")
        self.client.send("hello")
        # wait to receive c value
        c = self.client.receive()
        # generate H0
        H0 = bob.send_h0(c)
        # send H0 to alice
        self.client.send(H0)
        # wait for Alice to send h0, E, length as a payload
        (c_1, E, length) = self.client.receive()
        # compute response
        message = bob.getMessage(c_1, E, length).decode()
        return message

    def receiveGarbledTable(self, table=None):
        # wait to receive garbled table
        if table:
            self.garbledTable = table
        else:
            print("Waiting to receive garbled table from Alice..")
            self.garbledTable = self.client.receive()

    def evaluate(self, bobInputs):
        return bh.bobHandler(self.garbledTable, bobInputs)

    def determineInputWires(self):
        return self.garbledTable['bobIndex']

def loadJson(filepath):
    circ = None
    with open(filepath) as json_file:
        json_circuits = json.load(json_file)
        for json_circuit in json_circuits['circuits']:
            circ = circuit.Circuit(json_circuit)
            # break
    return circ

def perms(n):
    """
    Helper function to generate permutations for binary integers
    based on the length n.
    """
    if not n:
        return
    entries = []
    for i in range(2**n):
        s = bin(i)[2:]
        s = "0" * (n-len(s)) + s
        ent = [int(i) for i in s]
        entries.append(ent)
    return entries

if __name__ == "__main__":

    if sys.argv[1] == 'alice':
        a = Alice()
        print("this is alice")
        # json circuit
        circ = None
        if sys.argv[2]:
            jsonPath = sys.argv[2]

        circ = loadJson(jsonPath)
        # setup alices bits (do an iteration)
        alicesPotentialBits = perms(len(circ.alice))

        # wait for bob to send the payload saying that he is ready to compute.
        check = a.waitForBob()

        if check:
            for aliceBits in alicesPotentialBits:
                # compute garbled circuit and other
                # necessary things to transfer to bob.
                garbledCircuit = circ.sendToBob(aliceBits)
                referenceTable = garbledCircuit['referenceTable']

                # send this garbled circuit information to bob.
                a.transferGarbledCircuit(garbledCircuit)
                # wait for bob to request an oblivious transfer
                bob_resp = a.server.receive()
                if bob_resp == "start_ot":
                    print("initiating oblivious transfer.")
                    a.server.send("ok_ot")
                    # get bob input wires.
                    for i in garbledCircuit['bobIndex']:
                        print("iterating through",i)
                        # get the zero and one values from the garbled circuit.
                        input1, input2 = referenceTable[(i,0)],referenceTable[(i,1)]
                        a.obliviousTransfer(input1, input2)

                # compute oblivious transfer as a loop
                    # for i in numberOfBitsBobNeedsToGet:
                        # do oblivious transfer
                # wait for bob to evaluate the circuit
                # receive bob's evaluation to see whether the output 
                # is the same.
                # if it's the same then it works.
                break
     
    elif sys.argv[1] == 'bob':
        b = Bob()
        # 1. tell alice to initiate the transfer of the circuit
        b.initiate()
        # 1.1. receive garbled circuit.
        b.receiveGarbledTable()
        # 2. look at bob's input bits and see what he needs to recieve through the oblivious transfer
        print("Bob needs to get inputs for ",b.determineInputWires())

        for inputValues in perms(len(b.determineInputWires())):
            # 3. do oblivious transfer for each of the bits (in a loop)
            # 3.1 tell alice to start the oblivious transfer
            b.client.send("start_ot")
            inputs = []
            rsp = b.client.receive()
            if rsp == "ok_ot":
                # perform oblivious transfer for each of the inputs 
                for binary in inputValues:
                    print("Requesting oblivious transfer for value", binary)
                    response = b.obliviousTransfer(binary)
                    try:
                        inputs.append(response.encode())
                    except:
                        inputs.append(response)
            # 4. evaluate the garbled circuit when we have received all the bits.

            output = b.evaluate(inputs)
            print("GOT OUTPUT:", output)
            # 5. return output to alice.

    elif sys.argv[1] == 'local':
        a = Alice()
        b = Bob()
        # json circuit
        circ = None
        if sys.argv[2]:
            jsonPath = sys.argv[2]

        # circ = loadJson(jsonPath)
        with open(jsonPath) as json_file:
            json_circuits = json.load(json_file)
        for json_circuit in json_circuits['circuits']:
            circ = circuit.Circuit(json_circuit)
            print("circ name:", circ.name)
            if "NOT" in circ.name:
                continue
            print("P VALUE:", circ.p)
            # setup alices bits (do an iteration)
            alicesPotentialBits = perms(len(circ.alice))

            for aliceBits in alicesPotentialBits:
                # compute permutation of bobs bits.
                bobPotentialBits = perms(len(circ.bob))
                
                garbledCircuit = circ.sendToBob(aliceBits)
                for bobBits in bobPotentialBits:
                    # compute garbled circuit and other necessary 
                    # things to transfer to bob.
                    referenceTable = garbledCircuit['referenceTable']
                    # send this garbled circuit information to bob.
                    b.receiveGarbledTable(garbledCircuit)

                    bobInputValues = []
                    # start oblivious transfers
                    for i in range(len(garbledCircuit['bobIndex'])):
                        bobI = garbledCircuit['bobIndex'][i]
                        bobsValue = bobBits[i]
                        # get the zero and one values from the garbled circuit.
                        input1, input2 = referenceTable[(bobI,0)],referenceTable[(bobI,1)]
                        # set up ot
                        alice = ot.Alice(input1, input2)
                        bob = ot.Bob(bobsValue)

                        c = alice.send_c()
                        h0 = bob.send_h0(c)
                    
                        c_1, E, length = alice.sendMessage(h0)
                        # send c_1, E, length to Bob.
            
                        trueMsg = bob.getMessage(c_1,E, length)
                        bobInputValues.append(trueMsg)

                    # print("BOB INPUT:", bobInputValues)
                    # wait for bob to evaluate the circuit
                    output = b.evaluate(bobInputValues)
                    # receive bob's evaluation to see whether the output 
                    # is the same.
                    # if it's the same then it works.
                    print("A real:",aliceBits, "B real:",bobBits, "OUT:",output)
                    # break
                # break
            break