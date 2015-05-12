#coding: utf-8
import types, time
import csv, cStringIO, codecs
import xml.dom.minidom
import httplib
import urllib
import sys
import os
import simplejson
import logging
from pprint import pprint
from launchpadlib.launchpad import Launchpad
import dateutil.parser

CONST_TEAM = "trafodion"

def no_credential():
    print "Can't proceed without Launchpad credential."
    sys.exit()

def cleanID(id):
    # If this is a URL, return the leaf element
    lastSlash = id.rfind("/")
    if lastSlash == -1:
        return id
    else:
        lastSlash = lastSlash+1
        temp = str(id[lastSlash:])
        # If it now starts with ~, lose that
        if temp[0] == '~':
            temp = temp[1:]
        return temp
    
class Bug:
    createCsv = False
    LOG_FILENAME = 'logging_launchpad_bugs.out' 

    logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)

    if createCsv:    
        row1written = False

    def __init__(self):
        #launchpad = Launchpad.login_anonymously('just testing', 'production')
        launchpad = Launchpad.login_with('LaunchpadBugs.py','production',credential_save_failed=no_credential)

        p = launchpad.projects[CONST_TEAM]
        print p.display_name
        #bugTasks = p.searchTasks(search_text="file formats")
        #bugTasks = p.searchTasks(status=["Fix Released"],tags=["infrastructure"],search_text="CDN")
        #bugTasks = p.searchTasks(tags=["infrastructure"])
        #bugTasks = p.searchTasks(status=["Incomplete (with response)","Incomplete (without response)"])
        bugTasks = p.searchTasks(status=["New","Incomplete","Opinion","Invalid","Won't Fix","Expired","Confirmed","Triaged","In Progress","Fix Committed","Fix Released","Incomplete (with response)","Incomplete (without response)"])
        #bugTasks = p.searchTasks(status=["New","Confirmed","Fix Committed"],information_type=['Public','Public Security','Private Security','Private','Proprietary','Embargoed'])
        #bugTasks = p.searchTasks(status=["New","Incomplete","Opinion","Invalid","Won't Fix","Expired","Confirmed","Triaged","In Progress","Fix Committed","Fix Released","Incomplete (with response)","Incomplete (without response)"],tags=['infrastructure'])
        
        print "Number of bugs: " + str(len(bugTasks))
        bugHasAttachments = 0
        maxMessages = 0

        # launchpad json
        launchpadJson = Launchpad.login_with('lplib.cookbook.json_fetcher', 'production', '.lplib-json_fetcher-cache',credential_save_failed=no_credential)
        # authenticated browser object
        browser = launchpadJson._browser

        bugTargetDisplayName = ""
        bugTargetName = ""

        for bugTask in bugTasks:         
            # Extract the bug ID from the bug link
            bugKey = cleanID(bugTask.bug_link)
            bug = launchpad.bugs[bugKey]
            bugId = bug.id
            print "Bug ID is " + str(bugId)

            bugTaskTargetDisplayName = bugTask.bug_target_display_name
            bugTaskTargetName = bugTask.bug_target_name
            
            if bugTaskTargetName != bugTargetName:
                print "Bug id: " + str(bugId)
                print "Target name: " + bugTaskTargetName
                bugTargetName = bugTaskTargetName

            # check if this has been downloaded earlier already
            bugLastUpdated = bug.date_last_updated
            xmlBug = BugXmlDoc(bugId)

            if xmlBug.doesXmlFileExist(bugId, bugLastUpdated) == False:
                xmlBug.addNode("date_last_updated", str(bugLastUpdated))
            
                ownerLink = bug.owner_link

                if type(ownerLink) is not types.NoneType :
                    try:
                        bugTaskID = cleanID(bugTask.bug_link)
                        bug = launchpad.bugs[bugTaskID]
                        ownerID = cleanID(bug.owner_link)
                        owner = launchpad.people[ownerID]
                        reportedBy = owner.display_name
                    except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)
                        reportedBy = ""
                else :
                    reportedBy = ""
                
                if type(bugTask.assignee_link) is not types.NoneType :
                    assignedID = cleanID(bugTask.assignee_link)
                    assignedTo = launchpad.people[assignedID].display_name
                else :
                    assignedTo = ""

                if type(bugTask.milestone_link) is not types.NoneType :
                    milestone_link = bugTask.milestone_link

                    result = browser.get(milestone_link) 
                    result = simplejson.loads(result)
                    milestone_title = result["title"]
                else :
                    milestone_link = ""
                    milestone_title = ""

                if bug.duplicate_of_link != None :
                    duplicate_link = bug.duplicate_of_link

                    result = browser.get(duplicate_link) 
                    result = simplejson.loads(result)
                else:
                    duplicate_link = ""
                    duplicateBugId = ""

                if bug.duplicates_collection_link != None:
                    duplicates_collection_link = bug.duplicates_collection_link

                    result = browser.get(duplicates_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        xmlBug.addDuplicate(str(entry["id"]))
                else:
                    bug.duplicates_collection_link = ""

                xmlBug.addNode("bug_api_link", bugTask.bug_link, "api_links")
                xmlBug.addNode("bug_web_link", bug.web_link)
                xmlBug.addNode("bug_owner_link", bug.owner_link, "api_links")
                xmlBug.addNode("owner", reportedBy)
                xmlBug.addNode("assignee", assignedTo)
                xmlBug.addNode("milestone_link", milestone_link, "api_links")
                xmlBug.addNode("milestone_title", milestone_title[11:])
                xmlBug.addNode("duplicate_link", duplicate_link)
                xmlBug.addNode("duplicate_bug_id", duplicateBugId)

                bugTitle = bug.title
                bugStatus = bugTask.status
                if bugTask.status.startswith("Incomplete"):
					bugStatus = "Incomplete"
				
				# Bug Importance Map
                bug_importance_map = {'Critical':'Blocker', 'High':'Critical', 'Medium':'Major', 'Low':'Minor'}
                if bugTask.importance == "Undecided" or bugTask.importance == "Wishlist":
					bugImportance = bugTask.importance
                else:
					bugImportance = bug_importance_map[bugTask.importance]
					
                dateCreated = bugTask.date_created

                xmlBug.addNode("title", bugTitle)
                xmlBug.addNode("status", bugStatus)
                xmlBug.addNode("importance", bugImportance)
                xmlBug.addNode("created", str(dateCreated))

                if bug.tags != None :
					print "Tags: " + ', '.join(bug.tags)
					label_tags = ['data-corruption', 'regression', 'low-hanging-fruit', 'ops', 'performance', 'crash', 'hang']
					for tag in bug.tags:
						if tag == "infrastructure":
							xmlBug.addNode("component", "Build Infrastructure")
						elif tag not in label_tags:
							xmlBug.addNode("component", tag)
						elif tag in label_tags:
							xmlBug.addNode("label", tag)
                else:
                    print "Tags: None"

                xmlBug.addCData("description", bug.description)
                xmlBug.addNode("linked_branches_collection_link", bug.linked_branches_collection_link, "api_links")
                xmlBug.addNode("activity_link", bug.activity_collection_link, "api_links")

                try:
                    result = browser.get(bug.activity_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        #get person
                        personRaw = browser.get(entry["person_link"])
                        personJson = simplejson.loads(personRaw)
                    
                        person = personJson["display_name"]
                        oldvalue = ""
                        newvalue = ""
                        eMessage = ""
                        whatchanged = ""
                        datechanged = ""

                        if (entry["oldvalue"] != None):
                            oldvalue = entry["oldvalue"]

                        if (entry["newvalue"] != None):
                            newvalue = entry["newvalue"]

                        if (entry["message"] != None):
                            eMessage = entry["message"]

                        if (entry["whatchanged"] != None):
                            whatchanged = entry["whatchanged"]

                        if (entry["datechanged"] != None):
                            datechanged = entry["datechanged"]

                        xmlBug.addActivity(datechanged, oldvalue, newvalue, whatchanged, person, eMessage)

                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)

                # addComment(self, datecreated, selflink, person, subject, content):
                try:
                    result = browser.get(bug.messages_collection_link) 
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        #get person
                        personRaw = browser.get(entry["owner_link"])
                        personJson = simplejson.loads(personRaw)
                    
                        person = personJson["display_name"]
                        selflink = ""
                        subject = ""
                        content = ""
                        whatchanged = ""
                        datecreated = ""

                        if (entry["self_link"] != None):
                            selflink = entry["self_link"]

                        if (entry["subject"] != None):
                            subject = entry["subject"]

                        if (entry["content"] != None):
                            content = entry["content"]

                        if (entry["date_created"] != None):
                            datecreated = entry["date_created"]

                        if (content != bug.description): #description is also stored as a comment
                            xmlBug.addComment(datecreated, selflink, person, subject, content)

                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error when adding a comments node.")
                        logging.exception(e)

                # get branches
                try:
                    result = browser.get(bug.linked_branches_collection_link)
                    result = simplejson.loads(result)

                    for entry in result["entries"]:
                        branchlink = entry["branch_link"]
                        bresult = browser.get(branchlink)
                        bresult = simplejson.loads(bresult)
                        displayname = bresult["display_name"]
                        xmlBug.addBranch(displayname)
                except Exception, e:
                        logging.error("Bug with id " + str(bugId) + " caused the following error.")
                        logging.exception(e)

                messages = []
                
                i = 0
                                                
                if bug.message_count > 0:
                    for message in bug.messages:
                        if len(message.bug_attachments_collection_link) > 0:
                            # find the right attachment
                            for attachment in bug.attachments:
                                if (attachment.message_link == message.self_link):
                                    print "Attachment file link is ",attachment.data_link
                                    personID = cleanID(message.owner_link)
                                    xmlBug.addMessage(str(message.date_created), launchpad.people[personID].display_name, message.content, attachment)
                                    break
                        else:
                            personID = cleanID(message.owner_link)
                            xmlBug.addMessage(str(message.date_created), launchpad.people[personID].display_name, message.content)

                if bug.message_count > maxMessages:
                    maxMessages = bug.message_count

                xmlBug.writeToFile(bugId);

        print "Bugs with attachements: %s" % (bugHasAttachments)
        print "Max messages on one bug: %s" % (maxMessages)
    
        if self.createCsv:
            UnicodeWriter.createJiraCsv(csvWriter, "maria", bugTitle, assignedTo, reportedBy, bug.description, "", bugStatus, bugStatus, messages, str(dateCreated), "", "", "bug", "", "launchpad", bugImportance, bugStatus, bugStatus, "", "", "")

class BugXmlDoc:

    def __init__(self, id):
        # create root
        self.xmlDoc = xml.dom.minidom.getDOMImplementation().createDocument(None,"launchpad-bug",None)
        self.xmlDoc.documentElement.setAttribute("id", str(id)) 

    def addAttribute(self, nodeName, attribName, attribValue):
        node = self.xmlDoc.getElementsByTagName(nodeName)[0]
        node.setAttribute(attribName, attribValue)

    def addActivity(self, datechanged, oldvalue, newvalue, whatchanged, person, message):
        if self.xmlDoc.getElementsByTagName("activities").length < 1:
            activities = self.xmlDoc.createElement("activities")
            parent = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            parent.appendChild(activities)
        else:
            activities = self.xmlDoc.getElementsByTagName("activities")[0]

        activity = self.xmlDoc.createElement("activity")
        activity.setAttribute("datechanged", datechanged)
        nOldvalue = self.xmlDoc.createElement("oldvalue")
        txtOldvalue = self.xmlDoc.createCDATASection(oldvalue)
        nOldvalue.appendChild(txtOldvalue)
        activity.appendChild(nOldvalue)
        nNewvalue = self.xmlDoc.createElement("newvalue")
        txtNewvalue = self.xmlDoc.createCDATASection(newvalue)
        nNewvalue.appendChild(txtNewvalue)
        activity.appendChild(nNewvalue)
        nWhatchanged = self.xmlDoc.createElement("whatchanged")
        txtWhatchanged = self.xmlDoc.createTextNode(whatchanged)
        nWhatchanged.appendChild(txtWhatchanged)
        activity.appendChild(nWhatchanged)
        nPerson = self.xmlDoc.createElement("person")
        txtPerson = self.xmlDoc.createTextNode(person)
        nPerson.appendChild(txtPerson)
        activity.appendChild(nPerson)
        nMessage = self.xmlDoc.createElement("message")
        txtMessage = self.xmlDoc.createTextNode(message)
        nMessage.appendChild(txtMessage)
        activity.appendChild(nMessage)
        activities.appendChild(activity)

    def addComment(self, datecreated, selflink, person, subject, content):
        if self.xmlDoc.getElementsByTagName("comments").length < 1:
            comments = self.xmlDoc.createElement("comments")
            parent = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            parent.appendChild(comments)
        else:
            comments = self.xmlDoc.getElementsByTagName("comments")[0]

        comment = self.xmlDoc.createElement("comment")
        comment.setAttribute("datecreated", datecreated)
        comment.setAttribute("commentlink", selflink)
        nPerson = self.xmlDoc.createElement("person")
        txtPerson = self.xmlDoc.createTextNode(person)
        nPerson.appendChild(txtPerson)
        comment.appendChild(nPerson)
        nSubject = self.xmlDoc.createElement("subject")
        txtSubject = self.xmlDoc.createCDATASection(subject)
        nSubject.appendChild(txtSubject)
        comment.appendChild(nSubject)
        nContent = self.xmlDoc.createElement("content")
        txtContent = self.xmlDoc.createCDATASection(content)
        nContent.appendChild(txtContent)
        comment.appendChild(nContent)
        comments.appendChild(comment)

    def addDuplicate(self, bugId):
        if self.xmlDoc.getElementsByTagName("duplicates").length < 1:
            duplicates = self.xmlDoc.createElement("duplicates")
            parent = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            parent.appendChild(duplicates)
        else:
            duplicates = self.xmlDoc.getElementsByTagName("duplicates")[0]

        duplicateBug = self.xmlDoc.createElement("bug")
        duplicateBug.setAttribute("id", bugId)
        duplicates.appendChild(duplicateBug)

    def addBranch(self, branchname):
        if self.xmlDoc.getElementsByTagName("branches").length < 1:
            branches = self.xmlDoc.createElement("branches")
            parent = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            parent.appendChild(branches)
        else:
            branches = self.xmlDoc.getElementsByTagName("branches")[0]

        branch = self.xmlDoc.createElement("branch")
        branchTxt = self.xmlDoc.createTextNode(branchname)
        branch.appendChild(branchTxt)
        branches.appendChild(branch)

    def addMessage(self, created, owner, content, attachment = None):
        if self.xmlDoc.getElementsByTagName("messages").length < 1:
            messages = self.xmlDoc.createElement("messages")
            parent = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            parent.appendChild(messages)
        else:
            messages = self.xmlDoc.getElementsByTagName("messages")[0]

        message = self.xmlDoc.createElement("message")
        message.setAttribute("created", created)
        message.setAttribute("owner", owner)
        txt = self.xmlDoc.createCDATASection(content)
        message.appendChild(txt)

        if (attachment is not None):
            attachmentNode = self.xmlDoc.createElement("attachment")
            attachmentNode.setAttribute("type", attachment.type)
            attachmentNode.setAttribute("link", attachment.web_link)
            attachmentTitle = self.xmlDoc.createElement("title")
            txt = self.xmlDoc.createTextNode(attachment.title)
            attachmentTitle.appendChild(txt)
            attachmentNode.appendChild(attachmentTitle)
            attachmentFile = self.xmlDoc.createElement("file")

            print "Attachment title: ",attachment.title
            f_in = attachment.data.open()
            print "Attachment filename: ",f_in.filename

            fileName = "LPexportBug" + self.xmlDoc.documentElement.getAttribute("id") + "_" + f_in.filename

            if not os.path.exists(os.path.normpath(CONST_TEAM + "/attachment")):
                os.makedirs(os.path.normpath(CONST_TEAM + "/attachment"))

            builtName = os.path.normpath(CONST_TEAM + "/attachment/" + fileName)
            if not os.path.exists(builtName):
                f_out = open(builtName, 'wb')
                while 1:
                    copy_buffer = f_in.read(1024*1024)
                    if copy_buffer:
                        f_out.write(copy_buffer)
                    else:
                        break

                f_out.close()

            f_in.close()

            txtFile = self.xmlDoc.createTextNode(fileName)
            attachmentFile.appendChild(txtFile)
            attachmentNode.appendChild(attachmentFile)
            message.appendChild(attachmentNode)

        messages.appendChild(message)

    def addNode(self, name, content, parentName = "launchpad-bug"):
        element = self.xmlDoc.createElement(name)
        txt = self.xmlDoc.createTextNode(content)
        element.appendChild(txt)

        if self.xmlDoc.getElementsByTagName(parentName).length < 1:
            parent = self.xmlDoc.createElement(parentName)
            root = self.xmlDoc.getElementsByTagName("launchpad-bug")[0]
            root.appendChild(parent)
        else:
            parent = self.xmlDoc.getElementsByTagName(parentName)[0]

        parent.appendChild(element)

    def addCData(self, name, content, parentName = "launchpad-bug"):
        element = self.xmlDoc.createElement(name)
        txt = self.xmlDoc.createCDATASection(content)
        element.appendChild(txt)
        parent = self.xmlDoc.getElementsByTagName(parentName)[0]
        parent.appendChild(element)

    def getFileName(self, id):
        return "LPexportBug" + str(id) + ".xml"

    def doesXmlFileExist(self, id, lastUpdated):
        try:
            checkDoc = xml.dom.minidom.parse(os.path.normpath(CONST_TEAM + "/" + self.getFileName(id)))
            print "Found file: " + os.path.normpath(CONST_TEAM + "/" + self.getFileName(id))
        except IOError:
            print "Bug has not been fetched before, id: " + str(id)
            return False
        except:
            return False

        try:
            if dateutil.parser.parse(checkDoc.getElementsByTagName("date_last_updated")[0].firstChild.nodeValue) == lastUpdated:
                print "Bug hasn't changed since last fetched - no need to refetch, id: " + str(id)
                return True
            else:
                print "Bug has been updated since last fetched, id: " + str(id)
                return False
        except:
            return False

    def writeToFile(self, id):
        if not os.path.exists(CONST_TEAM):
            os.makedirs(CONST_TEAM)

        try:
            f = open(os.path.normpath(CONST_TEAM + "/" + self.getFileName(id)), "w")
            f.truncate() 
            f.write(self.xmlDoc.toprettyxml(indent="  ", encoding="utf-8"))
            f.close()
        except Exception, e:
            logging.error("Bug with id " + str(id) + " caused the following error.")
            logging.exception(e)


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

    def createJiraCsv(self, csvWriter, project, summary, assignee, reporter, description, components, affectsVersion, fixVersion, comments, dateCreated, dateModified, dueDate, issueType, subTasks, labels, priority, resolution, status, originalEstimate, remainingEstimate, timeSpent):
        
        """
        Project
        Summary
        Component(s)
        Affects Version(s)
        Fix Version(s)
        Comment Body - You can import issues with multiple comments by entering each comment in a separate column.
        Date Created
        Date Modified
        Due Date
        Issue Type
        Sub-Tasks 
        Labels
        Priority
        Resolution
        Status
        Original Estimate
        Remaining Estimate
        Time Spent
        """
        
        commentColumns = 29
        commentsFixed = []
        
        if (len(comments) < commentColumns):
            for comment in comments:
                commentsFixed.append(comment)

            for i in range(1, commentColumns - len(comments)):
                commentsFixed.append("");

        row = []
        row1 = []
        row.append(project)
        row1.append("project")
        row.append(summary)
        row1.append("summary")
        row.append(assignee)
        row1.append("assignee")
        row.append(reporter)
        row1.append("reporter")
        row.append(description)
        row1.append("description")
        row.append(components)
        row1.append("components")
        row.append(affectsVersion)
        row1.append("affects version(s)")
        row.append(fixVersion)
        row1.append("fix version(s)")

        for comment in commentsFixed:
            row.append(comment)
            row1.append("comment")
            
        row.append(dateCreated)
        row1.append("Date Created")
        row.append(dateModified)
        row1.append("Date Modified")
        row.append(dueDate)
        row1.append("Due Date")
        row.append(issueType)
        row1.append("Issue Type")
        row.append(subTasks)
        row1.append("Sub-Tasks")
        row.append(labels)
        row1.append("Labels")
        row.append(priority)
        row1.append("Priority")
        row.append(resolution)
        row1.append("Resolution")
        row.append(status)
        row1.append("Status")
        row.append(originalEstimate)
        row1.append("Original Estimate")
        row.append(remainingEstimate)
        row1.append("Remaining Estimate")
        row.append(timeSpent)
        row1.append("Time Spent")

        if self.row1written == False:
            csvWriter.writerow(row1)
            self.row1written = True
        
        csvWriter.writerow(row)

# start the script
Bug()
