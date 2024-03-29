import os
import json
import gates as gate
from cryptography.fernet import Fernet
import fern
import random
import array
import copy

class Circuit:
    def __init__(self,circuitDict, pBitOverride=None):
        """
        Circuit class to be computed by Alice. This means
        Alice knows the p
        """
        self.name = None
        self.alice = None
        self.bob = None
        self.gates = None
        self.out = None
        # processes json.
        self.processCircuit(circuitDict)
        # generate wire encryption keys
        self.generateWireKeys()
        # generate p bits
        self.generatePBits(override=pBitOverride)
        # load logic gates
        self.logic = gate.Gates()

    def processCircuit(self,circuit):
        """
        Loads the json and adds the relevant contents into the
        object.
        """
        for key in circuit.keys():
            setattr(self,key,circuit[key])
        self.raw = circuit
            
    def compute(self,inputs, encrypt=False):
        """
        Computes the gate operations and then returns the output.
        """
        # creates stores.
        limit = max([max(self.out),max([i['id'] for i in self.gates])])
        # create array to reference values at.
        store = [0 for i in range(limit+1)]

        # store inputs
        input_ids = self.alice+self.bob if self.bob else self.alice
        for i in input_ids:
            store[i] = inputs.pop(0)
        
        # iterate through the gate operations
        for gate in self.gates:
            # load logic gate
            logic = getattr(self.logic,gate['type'])
            # load inputs
            if encrypt:
                parameters = tuple([self.xor(store[i],self.p[i]) for i in gate['in']])
            else:
                parameters = tuple([store[i] for i in gate['in']])
            # get output
            result = logic(parameters)
            # store result
            store[gate['id']] = result
        
        if encrypt:
            return [self.xor(store[i],self.p[i]) for i in self.out]
        else:
            return [store[i] for i in self.out]
    
    def generateWireKeys(self):
        wire_count = max([max(self.out),max([i['id'] for i in self.gates])])
        # generate arbitary zeros and ones
        w = [[Fernet.generate_key() for j in range(0,2)] for i in range(wire_count+1)]
        # assign values.
        self.w = w
    
    def generatePBits(self, override=None, kill=False):
        """
        generates random p bits.
        these are the colouring bits on each wire.
        """
        # each wire w has two random keys (consult p28)
        w = override if override else []
        # get max limit of the gates.
        wire_count = max([max(self.out),max([i['id'] for i in self.gates])])
        
        if override and (len(override) != wire_count):
            print("YOUR P BITS WONT WORK.")
        # generate arbitary zeros and ones
        w = [random.choice([0,1]) for i in range(wire_count+1)]
        if kill:
            w = [0 for i in range(wire_count+1)]
        self.p = w
    
    def printRow(self, alice, bob, encrypt=False):
        """
        Prints an individual row given inputs from alice and bob.
        alice and bob are lists of binary values i.e [0,0,1]
        """
        if bob:
            inputs = alice + bob
            pr = "Alice"+str(self.alice)+" = " 
            for i in alice:
                pr += str(i) + " "
            pr += "  Bob"+str(self.bob)+" = "
            for i in bob:
                pr += str(i) + " "
            pr += "  Outputs"+str(self.out)+" = "
            for i in self.compute(inputs,encrypt=encrypt):
                pr += str(i) + " "
            print(pr)
        else:
            inputs = alice
            pr = "Alice"+str(self.alice)+" = " 
            for i in alice:
                pr += str(i) + " "
            pr += "  Outputs"+str(self.out)+" = "
            for i in self.compute(inputs,encrypt=encrypt):
                pr += str(i) + " "
            print(pr)
    
    def printall(self, encrypt=False):
        """
        Helper function to handle printing as is specified in the
        coursework notes.
        """
        print(self.name)
        for alice in self.perms(len(self.alice)):
            if self.bob:
                for bob in self.perms(len(self.bob)):
                    self.printRow(alice,bob,encrypt=encrypt)
            else:
                self.printRow(alice,bob=None,encrypt=encrypt)
        print()
        
    def generateGarbledCiruitTables(self,encrypt=True):
        """
        Computes the gate operations and then returns the output.
        """   
        garbledTables = []
        
        refEncryption = {}
        # iterate through the gate operations
        for gate in self.gates:
            # load logic gate
            gateTables = {}
            # print(gate.keys())
            logic = getattr(self.logic,gate['type'])

            # generate permutations of inputs.    
            for binaryInputs in self.perms(len(gate['in'])):

                encryptedInput = []
                # encrypt the values with w, and then XOR with p.
                for i in range(len(gate['in'])):
                    wire, value = gate['in'][i], binaryInputs[i]
                    # set up the fern encryptor.
                    value = self.xor(value,self.p[wire])
                    keypair = (wire,value)
                    if keypair not in refEncryption:
                        encryptedValue = fern.encryptInput(self.w[wire][value], value)
                        refEncryption[keypair] = encryptedValue
                    else:
                        encryptedValue = refEncryption[keypair]

                    encryptedInput.append((wire,encryptedValue))
                    # print result
                    # print("wire:", wire, "val:",value, " p["+str(wire)+"]:",self.p[wire], "w:", self.w[wire][value][-10:-2],"enc:",encryptedValue[-10:-2])
                
                # use the raw data as the tuple
                parameters = tuple(binaryInputs)
                # get output
                result = logic(parameters)
                # xor output with p value
                xoredResult = self.xor(result, self.p[gate['id']])
                # encrypt output
                encryptedOutput = fern.encryptInput(self.w[gate['id']][result], xoredResult)

                # store result in ref key
                # refKey = (gate['id'], xoredResult)
                # if refKey not in refEncryption:
                #     refEncryption[refKey] = encryptedOutput
                # else:
                #     encryptedOutput = refEncryption[refKey]

                # generate dictionary entry
                dictionaryInput = tuple(encryptedInput)
                dictionaryOutput = (gate['id'],encryptedOutput)

                gateTables[dictionaryInput] = dictionaryOutput
            garbledTables.append(gateTables)
        return (garbledTables, refEncryption)
         
    def sendToBob(self,aliceInput):
        # garble the table
        (garbled, referenceTable) = self.generateGarbledCiruitTables()
        # get wire keys
        w = self.w
        # get alice's encrypted bits
        encryptedBits = []
        
        if len(aliceInput) != len(self.alice):
            print("Alice's inputs aren't the same size.")
            return

        # aliceEncryptedBits = []
        # for i in range(len(aliceInput)):
        #     aliceWire = self.alice[i]
        #     aliceValue = aliceInput[i]
        #     aliceValue = self.xor(aliceValue, self.p[aliceWire])
        #     encryptedBit = referenceTable[(aliceWire, aliceValue)]
        #     aliceEncryptedBits.append((aliceWire, encryptedBit))

        # print("Generating Alice's encrypted values.")
        # print("ALICE INPUTS:", aliceInput)
        # print("P:",self.p)
        for i in range(len(aliceInput)):
            aliceWire = self.alice[i]
            aliceValue = aliceInput[i]
            # xor before encryption..
            aliceValue = self.xor(aliceValue, self.p[aliceWire])
            encryptedValue = fern.encryptInput(self.w[aliceWire][aliceValue], aliceValue)

            print("alice before w:", aliceWire, "v:", aliceValue, "v':", aliceValue)
            # print data
            # print("AWir:", aliceWire, "val:", aliceValue, " p["+str(aliceWire)+"]:", self.p[aliceWire], "w:",self.w[aliceWire][aliceValue][-10:-2], "enc:", encryptedValue[-10:-2])
            encryptedBits.append(encryptedValue)
            
        # get decryption bit for output wire
        outputDecryptionBits = [self.p[i] for i in self.out]

        # setup gate construction (w/o the labels)
        gateSet = copy.deepcopy(self.gates)
        for i in range(len(gateSet)):
            gateSet[i].pop('type', None)
        
        # get the p values for wires corresponding to bob's inputs.
        bobColouringValues = [self.p[i] for i in self.bob]

        return {
            'table'  : garbled,
            'w'      : w,
            'aliceIn': encryptedBits,
            'aliceIndex' : self.alice,
            'bobIndex' : self.bob,
            'bobColouring' : bobColouringValues,
            'gateSet' : gateSet,
            'numberOfIndexes' : max([max(self.out),max([i['id'] for i in self.gates])]),
            'outIndex' : self.out,
            'outputP': outputDecryptionBits,
            'referenceTable' : referenceTable
        }
        
    @staticmethod
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
    
    @staticmethod
    def xor(value, key):
        # use once to encrypt
        # twice to decrypt
        if value == key:
            return 0
        return 1


if __name__ == "__main__":
    folderpath = "../json"
    for file in os.listdir(folderpath):
        filename = os.path.join(folderpath,file)
        with open(filename) as json_file:
            json_circuits = json.load(json_file)
            for json_circuit in json_circuits['circuits']:
                circuit = Circuit(json_circuit)
#         print(circuit.name)
                if "Smart" in circuit.name:
#             circuit.printRow([0,0], [0,0])
                    circuit.printall(encrypt=False)
    #         print(circuit.p)
    #         garble  = GarbledCircuit(circuit)
    #         print(circuit.raw)
                break
        
	#     break
    
	# loadall()
