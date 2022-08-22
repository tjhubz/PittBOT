"""
This class will take in the path to the command_list.json file and the name of the command
that the user wants a description/info of/on.

the format of the output is as follows:
[embed title, command description, permissions, parameter/(inputs) descriptions, command type]

---

the embed title is self explanatory: it is the title of the embed and in this case, the name of the command.

the command description is the description of the command (duh).

permissions is just a list of the permissions needed for the command to be executed

parameter description is the description of the command's inputs. (i was personally thinking that
the embed name should be something like "inputs" or "input descriptions")

and the command type is just "Slash Command" and/or "User Context Menu"

----------------------------------------------------------------

quick code example:
                                    the path      the command
thelist = helpCommandOutput("./command_list.json", "verify").output()
print(thelist)

"""

import orjson
class HelpCommandOutput:
    def __init__(self, path: str, commandName: str):
        """enter the path to the json file of the bot commands."""

        self.path = path

        # this will be the final output of data
        self.outputList = []

        # adding the title
        self.outputList.append(commandName)

        with open(self.path, "r") as f:
            jsonData = orjson.loads(f.read())
            commandDataJson = jsonData[commandName]

        # adding the description of the command
        self.outputList.append(commandDataJson["description"])

        # adding the permissions
        if commandDataJson["permissions"] == []:
            self.outputList.append("No permissions are needed to run this command.")
        else:
            thePermissions = ""
            for permission in commandDataJson["permissions"]:
                thePermissions = thePermissions + f" {permission}"
                self.outputList.append(f"To run this command you need the following permissions:{thePermissions}")

        # adding the parameter descriptions
        inputDescriptionText = ""
        for inputt in commandDataJson["parameters"]:
            # adding to the inputDescriptionText string in this format:
            # input name: "the description" \n
            inputDescriptionText = inputDescriptionText + inputt["name"] + ": \"" + inputt["description"] + "\"\n"
        self.outputList.append(inputDescriptionText)
        
        # adding the command type
        commandTypes = ""
        for command in commandDataJson["types"]:
            commandTypes = commandTypes + ", " + command
        commandTypes = commandTypes[2:len(commandTypes)]
        self.outputList.append(commandTypes)
    def output(self):
        return self.outputList
