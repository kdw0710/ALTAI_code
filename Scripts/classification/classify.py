import logging
import json
import pickle
import glob
import os

__location__=os.path.realpath(os.path.join(os.getcwd(),os.path.dirname(__file__)))

#HIC_TYPES_PODIUM=['IBG','IBS','IBB','OBG','OBS','OBB']
#CHIP_TYPES_PODIUM=['GOLD','SILVER','BRONZE']
CHIP_TYPES_PODIUM=['GOLD','SILVER','BRONZE', 'BRONZENOVBB']
CHIP_TYPES_XYLOLOGY=['WOOD']
CHIP_TYPES_MINERALOGY=['BRICK']
CHIP_TYPES=CHIP_TYPES_PODIUM+CHIP_TYPES_XYLOLOGY+CHIP_TYPES_MINERALOGY
HIC_TYPES=['IBG','OBG','OBS','OBB','OBZ']

PODIUM_CUTS={}
for chip_type in CHIP_TYPES_PODIUM:
    with open('%s/%s.json'%(__location__,chip_type)) as cutfile:
        PODIUM_CUTS[chip_type]=json.load(cutfile)

def classify_parameters_podium(parameters,chip_type):
    cuts=PODIUM_CUTS[chip_type]
    cats={}
    for parameter_name in cuts:
        if not parameter_name in parameters:
            cats[parameter_name]=None
        else:
            val=parameters[parameter_name]
            cut=cuts[parameter_name]
            cats[parameter_name]=cut[0]<=val and val<=cut[1]
    return cats

def classify_podium(parameters,chip_type):
    cats=classify_parameters_podium(parameters,chip_type)
    if all(cat is True for cat in cats.values()):
        return 'OK'
    elif None in cats.values():
        missing=[n for n,v in cats.items() if v is None]
        logging.debug('Parameter(s) %s is/are needed for chip classification but is/are not present. Returning "NK".'%', '.join(missing))
        return 'NK'
    else:
        return 'NK'

def classify_chip(parameters):
    for chip_type in CHIP_TYPES_PODIUM:
        if classify_podium(parameters,chip_type)=='OK':
            return chip_type
    return 'NK' 

def classify_chip_parameters(parameters):
    cats={}
    for chip_type in reversed(CHIP_TYPES_PODIUM):
        for key,val in classify_parameters_podium(parameters,chip_type).items():
            if key in cats:
                if val==True:
                    cats[key]=chip_type
            else:
                if val==True:
                    cats[key]=chip_type
                elif val==False:
                    cats[key]='NK'
                else:
                    cats[key]=None
    return cats

def classify_for_hic(parameters,hic_type):
    if hic_type=='IBG':
        return classify_podium(parameters,'GOLD')
    elif hic_type=='OBG' or hic_type=='OBS':
        return classify_podium(parameters,'SILVER')
    elif hic_type=='OBB':
        obb=classify_podium(parameters,'BRONZE')
        obs=classify_podium(parameters,'SILVER')
        if obb=='OK' and obs=='NK':
            return 'OK'
        else:
            return 'NK'
    elif hic_type=='OBZ':
        obb=classify_podium(parameters,'BRONZE')
        obz=classify_podium(parameters,'BRONZENOVBB')
        if obz=='OK' and obb=='NK':
            return 'OK'
        else:
            return 'NK'
#    elif hic_type in HIC_TYPES_PODIUM:
#        return classify_podium(parameters,hic_type)
#    elif hic_type in HIC_TYPES_XYLOLOGY:
#        logging.warning('No xylology, yet. Returning "NK".')
#        return 'NK'
    else:
        logging.warning('Unknown HIC type "%s". Returning "NK".'%hic_type)
        return 'NK'

def flatten(params):
    tmp={}
    flatten_rec('',params,tmp)
    return tmp

def flatten_rec(prefix,i,o):
    if isinstance(i,dict):
        for k,v in i.items():
            if prefix!='':
                flatten_rec('%s.%s'%(prefix,k),v,o)
            else:
                flatten_rec(k,v,o)
    else:
        o[prefix]=i

def read_parameter_file(base_path):
    try:
        return flatten(json.load(open('%s/analyse_output.json'%base_path,'r')))
    except IOError:
        pass
    try:
        return flatten(pickle.load(open('%s/analyse_output.p'%base_path,'rb')))
    except IOError:
        pass
    logging.warning('Neither analyse_output.json nor analyse_output.p found in directory "%s".',base_path)
    return {}

def get_chip_from_path(path):
    if 'TR00' in path: # path pattern of probestation with tray
        chip_id=path[path.find('CERN_PC')-11:path.find('CERN_PC')-1] 
        return chip_id
    else: # path pattern of probestation with wafer
        chip_id=path[path.find('CERN_PC')-14:path.find('CERN_PC')-1] 
        return chip_id

def classify_probecard_data(base_path):
    parameters=read_parameter_file(base_path)
    cats=classify_chip_parameters(parameters)
    global_cat=classify_chip(parameters)
    return global_cat,cats

if __name__=='__main__':
    import sys
    import re
    import glob
    sys.path.append('%s/../util'%__location__)
    from mangle_trayid import mangle_trayid,unmangle_trayid
    logging.basicConfig(level=logging.DEBUG)
    if len(sys.argv)==3:
        if re.match(r'T\d{6}W\d{1,2}[TB]',sys.argv[1]):
            tray_id=mangle_trayid(sys.argv[1])
        elif re.match(r'[A-Z0-9]{5}\d{2}[TB]',sys.argv[1]):
            tray_id=sys.argv[1]
        else:
            print('Usage classify.py TRAYID [basepath]')
       
        searchPath='{:s}/*/*/Chips/{:s}/*/CERN_PC/*/'.format(sys.argv[2],tray_id) 
        logging.info('Scanning through probecard test data for {:d} folders.'.format(len(glob.glob(searchPath))))
        folders=[]
        for data_path in glob.iglob(searchPath):
            folders.append(data_path)    
        folders.sort(reverse=True)
        chips={}
        for folder in folders:
            print(folder)
            chip=get_chip_from_path(folder)[-2:]
            if not chip in chips:
                chips[chip]=classify_probecard_data(folder)
        cats=['GOLD','SILVER','BRONZE','NK']
        for chip in sorted(chips.keys()):
            if not chips[chip] in cats:
                cats.append(chips[chip])
        for cat in cats:
            catchips=[chip for chip,c in chips.items() if c==cat]
            print('%8s : %2d => %s'%(cat,len(catchips),' '.join(sorted(catchips))))
        missing=[chip for chip in ['A1','A2','A3','A4','A5','A6','A7','A8','B1','B2','B3','B4','B5','B6','B7','B8','C2','C3','C4','C5','C6','C7','C8'] if chip not in chips]
        print('%8s : %2d => %s'%('MISSING',len(missing),' '.join(sorted(missing))))
                 
    else:
        print('Usage classify.py TRAYID [basepath]')



