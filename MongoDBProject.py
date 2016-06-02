#Imports
import xml.etree.cElementTree as ET
import pprint
import re
import string
from collections import defaultdict
import codecs
import json

#Regular Expressions
lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)

#Expected Values and Mapping Dictionary
expected = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place", "Square", "Lane", "Road", 
			"Trail", "Parkway", "Commons", "Broadway","Bridge", "Close","Buildings", "Centre",
			"Cloisters","Drove","East","Esplande",'Polygon','Cottages', 'West', 'Hill', 'Way',
			'North', 'Mews', 'Holt', 'Park', 'Queensway', 'South', 'Terrace', 'Greenways', 'Grove',
			'Mount', 'Finches']
			
mapping = { "St": "Street",
			"St.": "Street",
			"Ave": "Avenue",
			"Rd.": "Road",
			"Rd" : "Road",
			"Westal" : "West",
			"road" : "Road",
			"Raod" : "Road",
			"Street)" : "Street",
			}

#List for added values to JSON object from XML data
CREATED = [ "version", "changeset", "timestamp", "user", "uid"]            

##### Count Tag Function #####

#Count Tag Function - Checks how many of each type of tag are in the data and returns a dictionary
def count_tags(filename):
	tags = {}
	for elem in ET.iterparse(filename):
		new = elem[1].tag
		if new in tags:
			tags[new] += 1
		else:
			tags[new] = 1
	return tags        
			
#Calls Function. Uncomment this to run and print out the above function.

#pprint.pprint(count_tags('southampton_england.osm'))


##### Key Type Function #####

#Key Type Function, checks the key value in every tag element against regular expressions to (amongst other things) 
#help determine problems, has option to print out the problem values.
def key_type(element, keys):
	if element.tag == "tag":
		attr = element.attrib['k']
		if re.search(lower,attr):
			keys['lower'] += 1
		elif re.search(lower_colon,attr):
			keys['lower_colon'] += 1
		elif re.search(problemchars,attr):
			keys['problemchars'] += 1  
			#print "Found a problem attribute: " + attr
		else:
			keys['other'] += 1
			#print "Found a problem attribute: " + attr
		
	return keys



def process_key_types(filename):
	keys = {"lower": 0, "lower_colon": 0, "problemchars": 0, "other": 0}
	for _, element in ET.iterparse(filename):
		keys = key_type(element, keys)

	return keys

#Calls Function. Uncomment this to run and print out the above function. 
#pprint.pprint(process_key_types('southampton_england.osm'))


##### Audit Street Name Function #####


#Pulls the street type from the data and then audits it across the expected list and mapping dictionary.
def audit_street_type(street_types, street_name):
	m = street_type_re.search(street_name)
	if m:
		street_type = m.group()
		#If the street_type is not expected, add it to unexpected dictionary.
		if street_type not in expected:
			#Check to see if street_type is in mapping dictionary and saves the new name if it is.
			street_name = update_name(street_name,mapping)
			street_types[street_type].add(street_name)

#Checks to see if element has the address:street attribute and is therefore a street name.
def is_street_name(elem):
	return (elem.attrib['k'] == "addr:street")

#Update name function for replacing part of the adress with the mapping term, includes rreplace.
def update_name(name, mapping):

	for check in mapping:
		if check in name: 
			if mapping[check] not in name:
			 pos = name.index(check)
			 old_name = name
			 name = rreplace(name, check, mapping[check],1)
			 #Uncomment the below line to add a print out of the changes being made
			 #print "Found one, old name: " + old_name + " new name: " + name
			 

	return name

#Special function to only replace the last occurance of the mapping term, as to avoid bugs.
def rreplace(s, old, new, occurrence):
			li = s.rsplit(old, occurrence)
			return new.join(li)

#Function that will run the other parts of the code to actually perform the audit.
def audit_street_names(osmfile):
	osm_file = open(osmfile, "r")
	street_types = defaultdict(set)
	for event, elem in ET.iterparse(osm_file, events=("start",)):

		if elem.tag == "node" or elem.tag == "way":
			for tag in elem.iter("tag"):
				if is_street_name(tag):
					audit_street_type(street_types, tag.attrib['v'])

	return street_types  			

#Calls Function. Uncomment this to run and print out the above function. 
#st_types = audit_street_names('southampton_england.osm')
#pprint.pprint(dict(st_types))


##### Shape Element Function #####
#Used for preparing the XML data into an JSON object ready for upload to MongoDB 
def shape_element(element):
	node = {}
	node['pos'] = []
	node['node_refs'] = []
	node['address'] = {}
	node['seamark'] = {}
	node['created'] = {}
	if element.tag == "node" or element.tag == "way" :
		node['type'] = element.tag

		for elem_key, elem_value in element.attrib.items():
			#Creates a new embedded JSON object giving details on how this element was made.
			if elem_key in CREATED:
				node['created'][elem_key] = elem_value
			#Creates a position list to create a longitude and latitude, used for geo indexing    
			elif elem_key == "lat" or elem_key == "lon":
				node['pos'].append(float(elem_value))
			else:
				node[elem_key] = elem_value

		for tag in element:
			#Checks if it a tag element and that it contains no problem charecters
			if tag.tag == "tag" and re.search(problemchars,tag.attrib['k']) == None:

				if tag.attrib['k'].count(":") < 2:
					if tag.attrib['k'][:5] == "addr:":
						in_address_tag = [tag.attrib['k']][0][5:]
						#Checks for a postal code, and creates either a short form or long form key value pair
						if in_address_tag == "postcode" or in_address_tag == "postal_code":
							if 3 <= len(tag.attrib['v']) <= 4:
								node['address']['postalcodeshort'] = tag.attrib['v']
							else:
								node['address']['postalcodeshort'] = tag.attrib['v'][:5].strip()
						#Creates an embedded JSON object for address, with any first level sub attributes of address, second
						#level onwards are ignored.
						node['address'][in_address_tag] = tag.attrib['v']
					#Checks if the key element is a FIXME and assigns a new key value pair, potentialissue.	
					elif tag.attrib['k'] == "fixme" or tag.attrib['k'] == "FIXME":
						node['potentialissue'] = "Yes"
					#Creates a new embedded JSON object for seamark, with first level sub attributes of seamark
					elif tag.attrib['k'][:8] == "seamark:":
						in_seamark_tag = [tag.attrib['k']][0][8:]
						node['seamark'][in_seamark_tag] = tag.attrib['v']
					#Ensures naptan:Bearing attributes are not entered as being lowercase as this will create bugs into
					#future system imports
					elif tag.attrib['k'] == "naptan:Bearing":
						node[tag.attrib['k']] = tag.attrib['v']
					#Ensures all attribute key values are entered using lowercase	
					else:
						node[tag.attrib['k'].lower()] = tag.attrib['v']
			#If the main element tag is a 'way', and the tag of any inside object is a node, append it to a list of nodes,
			#labelled 'ref' 
			if tag.tag == "nd":
				node['node_refs'].append(tag.attrib['ref'])

		#Removes any empty fields that have been established but contain no information        
		if node['address'] == {}:
			del node['address']
		if node['seamark'] == {}:
			del node['seamark']	     
		if node['created'] == {}:
			del node['created']
		if node['node_refs'] == []:
			del node['node_refs'] 
		if node['pos'] == []:
			del node['pos']	   
		return node
	else:
		return None

#Creates a new json element taking in the OSM file and iterating over every line to create a new node for every point
#of data and outputs a new file.
def process_map_for_json(file_in, pretty = False):
	file_out = "{0}.json".format(file_in)
	data = []
	with codecs.open(file_out, "w") as fo:
		for _, element in ET.iterparse(file_in):
			el = shape_element(element)
			if el:
				data.append(el)
				if pretty:
					fo.write(json.dumps(el, indent=2)+"\n")
				else:
					fo.write(json.dumps(el) + "\n")
	return data

#Calls Function. Uncomment this to run the above function. 
#data = process_map_for_json('southampton_england.osm', False)

