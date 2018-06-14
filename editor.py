from jira import JIRA
from PySide import QtGui, QtCore, QtUiTools
from PIL import Image
import os
import json
import sys
import warnings

#TODO LIST:
#   1: Different attachment format support.
# X 2: Issue id case insensitive(all to captive)
#   3: Filter file types
# X 4: Show file details (time, uploader), also sortable
# X 5: Now vs Then 

#Qs:
#   1: Date format?

#Suppress all warning messages cuz they are annoying
warnings.filterwarnings("ignore")

class AttachmentEditor():
    def __init__(self, needs_auth=True):
        self.default_size = (775, 385)
        self.folded_size = (355, 385)
        self.folded = False
    
        self.app = QtGui.QApplication([])
        self.login_window = QtUiTools.QUiLoader().load("ui/login.ui")
        self.main_window = QtUiTools.QUiLoader().load("ui/main.ui")
        self.jira = None
        
        if os.path.exists("profile.json"):
            with open("profile.json", 'r') as f:
                j = json.load(f)
                self.server_url = j["server"]
                self.username = j["username"]
                self.password = j["password"]
        else:
            self.server_url = ""
            self.username = ""
            self.password = ""
        
        if (needs_auth):
            self.showLoginWindow()           
        else:
            self.launchMain()
            
        self.initial_loading_complete = False
        self.attachments_mapping = {}  # {filename: (file, id, sufix)...}
        self.original_attachments = {} # copy of above
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
            print e
            self.displayWarning("Failed", "Login failed. Please retry.")
            
        if success:
            user_info = {"server": self.server_url, "username": self.username, "password": self.password}
            with open("profile.json", 'w') as output:
                json.dump(user_info, output)
            self.displayInfo("Success", "You have logged in successfully!")
            self.launchMain()
        else:
            self.server_url = ""
            self.username = ""
            self.password = ""
            self.showLoginWindow()
            
    def launchMain(self):
        self.main_window.show()
        self.main_window.getButton.clicked.connect(self.getIssueById)
                
        self.original_tree = self.main_window.originalTree
        self.original_tree.itemDoubleClicked.connect(self.showAttachment)
        self.original_tree.header().setClickable(True)
        self.original_tree.header().sectionClicked.connect(self.sort_by_column)
        
        self.current_tree = self.main_window.currentTree
        self.current_tree.itemDoubleClicked.connect(self.triggerEditCurrent)
        self.current_tree.itemChanged.connect(self.attachmentRenamed)
        self.current_tree.itemSelectionChanged.connect(self.attachmentSelected)
        
        self.main_window.updateButton.clicked.connect(self.updateAttachments)
        self.main_window.hideOriginalButton.clicked.connect(self.foldOriginal)
                
    def getIssueById(self):
        msg = "Fetching data from JIRA server. Please wait..."
        self.initializeProgressBar(msg)
        id = self.main_window.issueId.text().upper()
        self.initial_loading_complete = False
        try:
            #Get issue object, its attachments and fill the data structures
            self.issue = self.jira.issue(id)
            attachments = self.issue.fields.attachment
            num_attachments = len(attachments)
            
            #Reset data structures
            self.attachments_mapping = {}  
            self.original_attachments = {}
            
            for idx, attachment in enumerate(attachments):
                file_name = str(attachment)
                file_sufix = '.' + str(attachment).split('.')[1]
                file_author = attachment.author.displayName
                file_created_date = attachment.created
                self.attachments_mapping[file_name] = (attachment.get(), attachment.id, file_sufix, file_author, file_created_date)
                self.refreshProgressBar(num_attachments, idx + 1)
                #print "getting", filename, self.attachments_mapping.keys()
            
            #Make a copy of the original attachments
            self.original_attachments = dict(self.attachments_mapping)
            
            #Add attachment names to display
            self.refreshDisplayPanel(self.original_tree, self.original_attachments)
            self.refreshDisplayPanel(self.current_tree, self.original_attachments, True)
           
            #print "ori = ", self.original_attachments.keys()
            #print "curr = ", self.attachments_mapping.keys()
            self.initial_loading_complete = True
            
        except Exception as e:
            warning_msg = "Issue <%s> not found! Please retry!" % str(id)
            self.displayWarning("Warning", warning_msg)
            #Shoot error message dialog
            self.main_window.issueId.clear()
        self.progress_window.close()
      
    def showAttachment(self, item, col):
        attachment_name = item.text(0)
        attachment_sufix = self.original_attachments[attachment_name][2]
        attachment_path = "attachments/" + attachment_name + attachment_sufix
        pic_sufixes = {".png": 1, ".PNG": 1, ".bmp": 1, ".BMP": 1, ".jpg": 1, ".JPG": 1, ".jpeg": 1, ".JPEG": 1}
        try:
            with open(attachment_path, 'wb') as output:
                output.write(self.original_attachments[attachment_name][0])
            if attachment_sufix in pic_sufixes:
                image = Image.open(attachment_path)
                image.show()
            else:
                #TODO text file support 
                self.text_window = QtUiTools.QUiLoader().load("ui/textPanel.ui")
                with open(attachment_path, 'r') as input:
                    content = input.read()
                    self.text_window.textDisplay.document().setPlainText(content)
                    self.text_window.show()

        except Exception as e:
            raise
            print "ERROR ", e
        
        print attachment_path
    
    def triggerEditCurrent(self, item, col):
        if col != 0:
            return
        self.current_tree.editItem(item, col)
    
    def attachmentSelected(self):
        if self.current_tree.currentItem():
            self.selectedAttachment = self.current_tree.currentItem().text(0)
        
    def attachmentRenamed(self, item, col):
        #print "called", self.initial_loading_complete, self.selectedAttachment
        if self.initial_loading_complete and self.selectedAttachment != "":
            new_name = item.text(0)
            self.attachments_mapping[new_name] = self.attachments_mapping.pop(self.selectedAttachment)
            self.selectedAttachment = new_name
            
    def updateAttachments(self):
        #Delete all changed
        for attachment in self.original_attachments:
            id = self.original_attachments[attachment][1]
            self.jira.delete_attachment(id)
            
        #Re-upload all changed
        success = False
        msg = "Updating attachments!"
        self.initializeProgressBar(msg)
        num_attachments = len(self.attachments_mapping)
        index = 0
        for attachment in self.attachments_mapping:
            sufix = self.attachments_mapping[attachment][2]
            f = self.attachments_mapping[attachment][0]
            file_name = attachment + sufix if sufix not in attachment else attachment
            #Create a local temp copy to upload
            with open(file_name, 'wb') as tmp_out:
                tmp_out.write(f)
            with open(file_name, 'rb') as to_upload:
                try:
                    self.jira.add_attachment(issue=self.issue, attachment=to_upload, filename=file_name) 
                    success = True
                    index += 1
                    self.refreshProgressBar(num_attachments, index)
                except Exception as e:
                    print e
            #Delete local copy
            os.remove(file_name)
        if success:
            self.displayInfo("Success", "Attachments have been renamed successfully.")
            self.selectedAttachment = ""
            self.getIssueById()
            #print "ori after = ", self.original_attachments.keys()
            #print "curr after = ", self.attachments_mapping.keys()
            a = 1
   
    #Using python JIRA module
    def connect_to_JIRA(self, server_url, auth):
        options = {'server': server_url, 'verify':False}
        jiraInstance = JIRA(options, basic_auth = auth, max_retries=0)
        return jiraInstance

    def foldOriginal(self):
        if (not self.folded):
            self.main_window.setFixedSize(self.folded_size[0], self.folded_size[1])
            self.main_window.hideOriginalButton.setText(">>")
            self.folded = True
        else:
            self.main_window.setFixedSize(self.default_size[0], self.default_size[1])
            self.main_window.hideOriginalButton.setText("<<")
            self.folded = False
 
    def refreshDisplayPanel(self, panel, content, editable=False, sort_key=None):
        while (panel.topLevelItemCount() > 0):
            panel.takeTopLevelItem(0)
            
        sorted_data = []
        for file_name in content:
            sorted_data.append((file_name, content[file_name]))
            
        if sort_key:
            sorting_method = None
            if sort_key == "Name":
                sorting_method = lambda x: x[0]
            elif sort_key == "Author":
                sorting_method = lambda x: x[1][3].split(' ')[0]
            elif sort_key == "Date":
                pass
            sorted_data = (sorted(sorted_data, key=sorting_method))[::-1]
            
        for data in sorted_data:
            file_name = data[0]
            author = data[1][3]
            date = data[1][4]
            item = QtGui.QTreeWidgetItem()
            item.setText(0, file_name)
            item.setText(1, author)
            item.setText(2, date)
            panel.insertTopLevelItem(0, item)
        
        if editable:
            for x in xrange(0, panel.topLevelItemCount()):
                item = panel.topLevelItem(x)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
    
    def sort_by_column(self, col):
        if col == 0:
            self.refreshDisplayPanel(self.original_tree, self.original_attachments, sort_key="Name")
        elif col == 1:
            self.refreshDisplayPanel(self.original_tree, self.original_attachments, sort_key="Author")
        elif col == 2:
            pass
        else:
            print "ERROR sorting!"
    
    def parseJiraTime(self, time):
        pass
    
    def initializeProgressBar(self, msg):
        self.progress_window = QtUiTools.QUiLoader().load("ui/progress.ui")
        self.progress_window.progressBar.setRange(0, 100)
        self.progress_window.progressBar.setValue(1)
        self.progress_window.messageLabel.setText(msg)
        self.progress_window.show()
    
    def refreshProgressBar(self, total, current):
        if self.progress_window:
            self.progress_window.progressBar.setRange(0, total)
            self.progress_window.progressBar.setValue(current)
    
    def displayWarning(self, title, msg):
        QtGui.QMessageBox.warning(self.main_window, title, msg)
    
    def displayInfo(self, title, msg):
        QtGui.QMessageBox.information(self.main_window, title, msg)
        
    
def testStuff():
    options = {'server': "https://hdc-tomcat-jira194.ubisoft.org/jira", 'verify':False}
    jira = JIRA(options, basic_auth = ("hui-cheng.zhuang@ubisoft.com","32194567ZHc"))
    issue = jira.issue("TES-3")
    attachments = issue.fields.attachment
    for attachment in attachments:
        name = str(attachment)
        #print attachment.__dict__.keys()
        #print attachment.author.__dict__.keys()
        print attachment.created, attachment.author.raw
        break
    sys.exit(0)  
    a = 1

def main():
    editor = AttachmentEditor()
    #jira_instance.add_attachment(issue=issue, attachment=file, filename="test.jpg")
    
if __name__ == "__main__":
    #testStuff()
    main()














