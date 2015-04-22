#!/usr/bin/env python

import sys
import requests
import json
import base64
from datetime import datetime

WORK_TEMPLATE = ('prefix cdm: <http://publications.europa.eu/ontology/cdm#> '
                'select distinct ?uri ?document_date '
                '(group_concat(distinct ?author;separator=", ") as ?authors) '
                '(group_concat(distinct ?identifier;separator=", ") as ?identifiers) '
                '(group_concat(distinct ?resource_type;separator=", ") as ?resource_types) '
                '(group_concat(distinct ?subject;separator=", ") as ?subjects) '
                'where {'
                '?uri owl:sameAs/cdm:work_created_by_agent/skos:prefLabel ?author;'
                'owl:sameAs/cdm:work_date_document ?document_date;'
                'owl:sameAs/cdm:work_id_document ?identifier;'
                'owl:sameAs/rdf:type ?resource_type.'
                'optional {?uri owl:sameAs/cdm:work_is_about_concept_eurovoc/skos:prefLabel ?subject.}'
                'filter (lang(?author)="en")'
                'filter (lang(?subject)="en")'
                'filter (?uri=<%(uri)s>)'
                '}'
                'group by ?uri ?document_date')

EXPRESSION_TEMPLATE = ('prefix cdm: <http://publications.europa.eu/ontology/cdm#>'
                      ' select distinct ?uri ?title ?lang where {'
                      '?uri owl:sameAs/cdm:expression_title ?title;'
                      'owl:sameAs/cdm:expression_uses_language/dc:identifier ?lang.'
                      'filter (?uri=<%(uri)s>)'
                      '}')
MANIFESTATION_TEMPLATE = ('prefix cdm: <http://publications.europa.eu/ontology/cdm#> '
                         'select distinct ?uri ?type ?lang '
                         'where {'
                         '?uri owl:sameAs/cdm:manifestation_type ?type; '
                         'owl:sameAs/cdm:manifestation_manifests_expression/^owl:sameAs/owl:sameAs/cdm:expression_uses_language/dc:identifier ?lang.'
                         'filter (?uri=<%(uri)s>)'
                         '}')

docs = {}
current_count = 0
word = None
sparql_endpoint = 'http://publications.europa.eu/webapi/rdf/sparql'
elastic_search_endpoint = 'http://opsvc086:9200//cellar/object/'
index_prefs = {'xhtml':0,'html':1,'pdfa1a':2,'pdf':3,'fmx4':4}


def reduce():
    # input comes from STDIN
    for line in sys.stdin:
        entry = {}
        # remove leading and trailing whitespace
        line = line.strip()
        # parse the input we got from mapper.py
        key, value = line.split('\t', 1)
        operation, id, type, ts = value.split(',')
        ts = datetime.strptime(ts.split('+')[0],'%Y-%m-%dT%H:%M:%S')
        if (docs.get(key)!=None):
            if(docs[key].get(id)!=None):
                if (ts >= docs[key][id][2]):
                    docs[key][id] = [operation, type, ts]
            else:
                docs[key][id] = [operation, type, ts]
        else:
            docs[key] = {}
            docs[key][id] = [operation, type, ts]
    #print(docs)
    return docs

def process(docs):
    query_string = None
    for k in docs.keys():
        for v in docs[k].keys():
            if(docs[k][v][0] == "CREATE" or docs[k][v][0] == "UPDATE"):
                if (docs[k][v][1]=='http://publications.europa.eu/ontology/cdm#work'):
                    query_string = WORK_TEMPLATE % {'uri':v.replace('cellar:','http://publications.europa.eu/resource/cellar/')}
                if (docs[k][v][1]=='http://publications.europa.eu/ontology/cdm#expression'):
                    query_string = EXPRESSION_TEMPLATE % {'uri':v.replace('cellar:','http://publications.europa.eu/resource/cellar/')}
                if (docs[k][v][1]=='http://publications.europa.eu/ontology/cdm#manifestation'):
                    query_string = MANIFESTATION_TEMPLATE % {'uri':v.replace('cellar:','http://publications.europa.eu/resource/cellar/')}
                sparql_result = sparql_query(query_string)
                if(sparql_result!=[]):
                    docs[k][v].append(post_process[docs[k][v][1]](sparql_result))
                else:
                    print(v+" is empty")
                    docs[k][v].append({})
            else:
                 docs[k][v].append({})
    for k in docs.keys():
        if(is_work_create(docs[k])):
            json_doc = add_attachment(create_new_document(docs[k]))
            #json.dump(json_doc, sys.stdout,indent=4, sort_keys=True )
            put_into_index(k, json.dumps(json_doc))


def post_process_work_result(result):
    uri = result[0]['uri']['value']
    document_date = result[0]['document_date']['value']
    authors = result[0]['authors']['value'].replace(", ",",").split(',')
    identifiers = result[0]['identifiers']['value'].replace(", ",",").split(',')
    resource_types = result[0]['resource_types']['value'].replace(", ",",").split(',')
    subjects = result[0]['subjects']['value'].replace(", ",",").split(',')
    return {'uri':uri,'document_date':document_date,'authors':authors,'identifiers':identifiers,
            'resource_types':resource_types,'subjects':subjects}

def post_process_expression_result(result):
    lang = result[0]['lang']['value']
    uri = result[0]['uri']['value']
    title = result[0]['title']['value']
    return {'uri':uri,'title'+'_'+str(lang).lower():title}

def post_process_manifestation_result(result):
    lang = result[0]['lang']['value']
    uri = result[0]['uri']['value']
    type = result[0]['type']['value']
    text = ""
    return {'uri':uri,'type':type, 'text'+'_'+str(lang).lower():text, 'lang':lang}

def is_work_create(doc):
    for k in doc.keys():
        if (doc[k][0]=='CREATE' and doc[k][1]=='http://publications.europa.eu/ontology/cdm#work'):
            return True
    return False

post_process = {'http://publications.europa.eu/ontology/cdm#work':post_process_work_result,
                'http://publications.europa.eu/ontology/cdm#expression':post_process_expression_result,
                'http://publications.europa.eu/ontology/cdm#manifestation':post_process_manifestation_result}

def create_new_document(doc):
    registered_format = {}
    jsonDocument = {}
    for k in doc.keys():
        if (doc[k][1]=='http://publications.europa.eu/ontology/cdm#work' and doc[k][3]!={}):
            jsonDocument['work'] = [doc[k][3]]
        if(doc[k][1]=='http://publications.europa.eu/ontology/cdm#expression' and doc[k][3]!={}):
            if(jsonDocument.get('expressions')!=None):
                jsonDocument['expressions'].append(doc[k][3])
            else:
                jsonDocument['expressions'] = [doc[k][3]]
        if(doc[k][1]=='http://publications.europa.eu/ontology/cdm#manifestation' and doc[k][3]!={}):
            attachment_key = sorted(list(doc[k][3].keys()))[1]
            attachment_format = doc[k][3]['type']
            if(jsonDocument.get('manifestations')!=None):
                if(attachment_key in registered_format.keys()):
                    if (index_prefs[registered_format[attachment_key][0]]>index_prefs[attachment_format]):
                        jsonDocument['manifestations'][registered_format[attachment_key][1]] = doc[k][3]
                else:
                    jsonDocument['manifestations'].append(doc[k][3])
                    registered_format[attachment_key]= (doc[k][3]['type'], len(jsonDocument['manifestations'])-1)
            else:
                jsonDocument['manifestations'] = [doc[k][3]]
                registered_format[attachment_key]= (doc[k][3]['type'], len(jsonDocument['manifestations'])-1)
    return jsonDocument

def sparql_query(query, format="application/json"):
    """perform sparql query and return the corresponding bindings"""
    payload = {
        "default-graph-uri": "",
        "query": query,
        "debug": "on",
        "timeout": "",
        "format": format
    }
    resp = requests.get(sparql_endpoint, params=payload)
    if format == "application/json":
        json_results = json.loads(str(resp.text))
        json_results = json.loads(str(resp.text))
        return json_results['results']['bindings']
    return resp.text

def add_attachment(jsonDocument):
    manifestations = []
    if ('manifestations' in jsonDocument.keys()):
        for m in jsonDocument['manifestations']:
            attachment = get_attachment(m['uri'])
            m['text_'+m['lang'].lower()]= attachment
            manifestation = {'uri':m['uri'], 'type':m['type'], 'text_'+m['lang'].lower():attachment}
            manifestations.append(manifestation)
        jsonDocument['manifestations'] = manifestations
    return jsonDocument

def get_attachment(uri):
    headers = {"Accept":"text/html,application/xhtml+xml,application/pdf;type=pdfa1a"}
    resp = requests.get(uri, headers=headers)
    return base64.b64encode(resp.text.encode('utf-8')).decode()


def put_into_index(id, doc):
    resp = requests.put(url=elastic_search_endpoint+id,data=doc)
    print(resp.text)

if __name__ == '__main__':
    process(reduce())

