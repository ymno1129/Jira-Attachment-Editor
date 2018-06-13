from jira import JIRA
from PySide import QtGui, QtCore, QtUiTools
from PIL import Image
import os
import json
import sys
import warnings

#TODO LIST:
#   1: Different attachment format support.
#   2: Issue id case insensitive(all to captive)
#   3: Filter file types
#   4: Show file details (time, uploader), also sortable
#   5: Now vs Then 


#Suppress all warning messages cuz they are annoying
warnings.filterwarnings("ignore")

class AttachmentEditor():
    def __init__(self, needs_auth=True):
        self.default_size = (655, 385)
        self.folded_size = (355, 385)
        self.folded = False
    
        self.app = QtGui.QApplication([])
        self.login_window = QtUiTools.QUiLoader().load("ui/login.ui")
        self.main_window = QtUiTools.QUiLoader().load("ui/main.ui")
        self.jira = None
        
        with open("profile.json", 'r') as f:
            j = json.load(f)
            self.server_url = j["server"]
            self.username = j["username"]
            self.password = j["password"]
           
        if (needs_auth):
            self.showLoginWindow()           
        else:
            self.launchMain()
            
        self.initial_loading_complete = False
        self.attachments_mapping = {}  # {filename: (file, id, sufix)...}
        self.original_attachments = {} # copy of above
        self.changed_attachments = []  # [(old, new)...]
        self.selectedAttachment = ""
        
        self.app.exec_()

    def showLoginWindow(self):
        self.login_window.show() 
        self.login_window.server.setText(self.server_url)
        self.login_window.username.setText(self.username)
        self.login_window.password.setText(self.password)
        self.login_window.accepted.connect(self.confirmLogin)
        
    def confirmLogin(self):
        self.server_url = self.login_window.server.text()
        self.username = self.login_window.username.text()
        self.password = self.login_window.password.text()
        
        success = False
        
        try:
            self.jira = self.connect_to_JIRA(self.server_url, auth=(self.username, self.password))
            success = True
        except Exception as e:
            print "Login Failed! Please Re-try!"
            
        if success:
            print self.server_url, "connected"
            self.launchMain()
        else:
            self.showLoginWindow()
            
    def launchMain(self):
        self.main_window.show()
        self.main_window.getButton.clicked.connect(self.getIssueById)
        #self.attachment_list = self.main_window.attachments
        #self.attachment_list.itemDoubleClicked.connect(self.showAttachment)
        #self.attachment_list.itemChanged.connect(self.attachmentRenamed)
        #self.attachment_list.itemSelectionChanged.connect(self.attachmentSelected)
        #self.main_window.updateButton.clicked.connect(self.updateAttachments)
        self.main_window.hideOriginalButton.clicked.connect(self.hideOriginal)
                
    def getIssueById(self):
        id = self.main_window.issueId.text()
        self.initial_loading_complete = False
        try:
            #Reset data structures
            self.attachments_mapping = {}
            self.original_attachments = {}
            self.changed_attachments = []
            
            #Get issue object, its attachments and fill the data structures
            self.issue = self.jira.issue(id)
            attachments = self.issue.fields.attachment
            for attachment in attachments:
                file_name = str(attachment).split('.')[0]
                file_sufix = '.' + str(attachment).split('.')[1]
                self.attachments_mapping[file_name] = (attachment.get(), attachment.id, file_sufix)
                #print "getting", filename, self.attachments_mapping.keys()
            
            #Make a copy of the original attachments
            self.original_attachments = dict(self.attachments_mapping)
            
            #Add attachment names to display
            self.attachment_list.clear()
            self.attachment_list.addItems(self.attachments_mapping.keys())
            
            #Set file names editable (any better options?)
            for x in xrange(0, self.attachment_list.count()):
                item = self.attachment_list.item(x)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            
            #print "ori = ", self.original_attachments.keys()
            #print "curr = ", self.attachments_mapping.keys()
            self.initial_loading_complete = True
            
        except Exception as e:
            print "ERROR ", e
            self.attachments_mapping = {}
            self.original_attachments = {}
            self.changed_attachments = []
            self.attachment_list.clear()
            self.main_window.issueId.clear()
      
    def showAttachment(self, item):
        attachment_name = item.text()
        attachment_sufix = self.attachments_mapping[attachment_name][2]
        attachment_path = "attachments/" + attachment_name + attachment_sufix
        try:
            with open(attachment_path, 'wb') as output:
                output.write(self.attachments_mapping[attachment_name][0])
            image = Image.open(attachment_path)
            image.show()
        except Exception as e:
            print "ERROR ", e
        
        print attachment_path
    
    def attachmentSelected(self):
        self.selectedAttachment = self.attachment_list.currentItem().text()
    
    def attachmentRenamed(self, item):
        #print "called", self.initial_loading_complete
        if self.initial_loading_complete and self.selectedAttachment != "":
            new_name = item.text()
            self.attachments_mapping[new_name] = self.attachments_mapping.pop(self.selectedAttachment)
            self.selectedAttachment = new_name
    
    def updateAttachments(self):
        #Delete all changed
        for attachment in self.original_attachments:
            id = self.original_attachments[attachment][1]
            self.jira.delete_attachment(id)
            
        #Re-upload all changed
        success = False
        for attachment in self.attachments_mapping:
            sufix = self.attachments_mapping[attachment][2]
            f = self.attachments_mapping[attachment][0]
            file_name = attachment + sufix
            #Create a local temp copy to upload
            with open(file_name, 'wb') as tmp_out:
                tmp_out.write(f)
            with open(file_name, 'rb') as to_upload:
                try:
                    self.jira.add_attachment(issue=self.issue, attachment=to_upload, filename=file_name) 
                    success = True
                except Exception as e:
                    print e
                    #TODO make it more secure?
            #Delete local copy
            os.remove(file_name)
            
        if success:
            print "Renaming done!"
            self.selectedAttachment = ""
            self.getIssueById()
            #print "ori after = ", self.original_attachments.keys()
            #print "curr after = ", self.attachments_mapping.keys()
        
    
    #Using python JIRA module
    def connect_to_JIRA(self, server_url, auth):
        options = {'server': server_url, 'verify':False}
        jiraInstance = JIRA(options, basic_auth = auth, max_retries=0)
        return jiraInstance

    def hideOriginal(self):
        if (not self.folded):
            self.main_window.setFixedSize(self.folded_size[0], self.folded_size[1])
            self.main_window.hideOriginalButton.setText(">>")
            self.folded = True
            self.main_window.hideOriginalButton.clicked.connect(self.expandOriginal)

    def expandOriginal(self):
        if (self.folded):
            self.main_window.setFixedSize(self.default_size[0], self.default_size[1])
            self.main_window.hideOriginalButton.setText("<<")
            self.folded = False
            self.main_window.hideOriginalButton.clicked.connect(self.hideOriginal)
    
        
def testStuff():
    #options = {'server': "https://hdc-tomcat-jira194.ubisoft.org/jira", 'verify':False}
    #jira = JIRA(options, basic_auth = ("hui-cheng.zhuang@ubisoft.com","32194567ZHc"))
    #issue = jira.issue("TES-3")
    #with open('attachments/alps.jpg', 'rb') as f:
    #    print type(f)
    #    jira.add_attachment(issue=issue, attachment=f, filename="test.jpg")
    #attachments = issue.fields.attachment
    #for attachment in attachments:
    #    name = str(attachment)
    #    if name == "alps.jpg":
    #        print type(attachment.get())
    #sys.exit(0)  
    a = 1

def main():
    editor = AttachmentEditor(False)
    #jira_instance.add_attachment(issue=issue, attachment=file, filename="test.jpg")
    
if __name__ == "__main__":
    main()














