from classification import *

class Test(object):
    def __init__(self,name,description):
        self.name       =name
        self.description=description

    def path(self):
        return self.name.replace(' ','_')
      
    def abort_on_failure(self):
        return False

    def classify_iteratively(self,analysis_results,rules,classification_result):
        global_result=[]
        for key, rule in rules.items():
          if isinstance(rule, list): # list of classification objects
            classification_result[key] = CLASSIFICATION_BAD
            for classifier in rule:
              if classifier.in_range(analysis_results[key]):
                classification_result[key] = classifier.category
            global_result.append(classification_result[key]) 
          else:
            classification_result[key]={}
            global_result.append(self.classify_iteratively(analysis_results[key],rule,classification_result[key]))
        return Classification.combine_classification(global_result)
            
    def classify(self,analysis_results,rules):
        classification_result={}
        global_result=self.classify_iteratively(analysis_results,rules,classification_result)
        return { "global": global_result, "details": classification_result }
