import datetime

import numpy as np
from sklearn.base import TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer 

import structured_data_extractor
import build_graphs
import loader
import extract_data
import language_processing

class SexTransformer(TransformerMixin):
    """
    transforms EMPI into 'male', 'female' column
    """
    def fit(self, X, y = None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_sex, X)
        return np.matrix(transformed_X).transpose()

    def get_sex(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        if 'Sex' in person:
            sex = person['Gender']
            return int(sex == 'Female\r\n')
        else:
            return 0

    def get_feature_names(self):
        return ["sex_female"] 

class GetConcatenatedNotesTransformer(TransformerMixin):
    """Takes as input the type of note (i.e. 'Car' or 'Lno').
    For each empi x in the input vector X, it returns a concatentation of
    all the pre-procedure notes of the type specified for the patient with that empi."""
    def __init__(self, note_type, look_back_months=None):
        self.type = note_type
        self.look_back_months = look_back_months

    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_concatenated_notes, X)
        return transformed_X 

    def get_concatenated_notes(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        date_key = extract_data.get_date_key(self.type)
        notes = []
        sec_per_month = 24 * 60 * 60 * (365.0 / 12)
        if self.type in person.keys() and date_key != None:
            for i in range(len(person[self.type])):
                doc = person[self.type][i]
                date = extract_data.parse_date(doc[date_key])
                if date != None and date < operation_date:
                    if self.look_back_months and (operation_date - date).total_seconds() > (self.look_back_months * sec_per_month):
                        continue
                    notes.append(doc['free_text'])
        return '\n\n'.join(notes)        

class GetLatestNotesTransformer(TransformerMixin):
    """Similar to the transformer above, but takes in an extra parameter max_notes
    that limits the number of notes to incorporate, indexed from the procedure
    date going back in time, and returns an array of notes instead of a concatentation.
    For example, if you put max_notes to be 1, then it would return a single-element
    array with the text of the note closest to, but not including, the procedure date
    (for each empi in the input vector).""" 
    def __init__(self, note_type, max_notes):
        self.type = note_type
        self.max_notes = max_notes

    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_latest_concatenated_notes, X)
        return transformed_X 

    def get_feature_names(self):
        names = ['latest_note_' + str(i) for i in range(self.max_notes)]
        return np.array(names) 

    def get_latest_concatenated_notes(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        date_key = extract_data.get_date_key(self.type)
        notes = []
        if self.type in person.keys() and date_key != None:
            time_key_pairs = []
            for i in range(len(person[self.type])):
                doc = person[self.type][i]
                date = extract_data.parse_date(doc[date_key])
                if date != None and date < operation_date:
                    time_key_pairs.append((operation_date - date, i))
            time_key_pairs.sort()
            for time,key in time_key_pairs[:self.max_notes]:
                doc = person[self.type][key]
                notes.append(doc['free_text'])
        # ensure that notes vector length is equal to max_notes
        if len(notes) < self.max_notes:
            delta = self.max_notes - len(notes)
            for i in range(delta):
                notes.append('')  
        return np.array(notes)

class DocumentConcatenatorTransformer(TransformerMixin):
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.concatenate_notes, X)
        return transformed_X 

    def concatenate_notes(self, docs):
        return '\n\n'.join(docs)

class MultiDocTfidfTransformer(TransformerMixin):
    """
    Returns a vector of TFIDF vectors for each string in a vector. TFIDF
    weightings are global across all elements of the document.
    """
    def __init__(self):#, ngram_range=(1,1)):
        self.tfidf = TfidfVectorizer()#ngram_range=ngram_range)
        self.vec_size = 0 

    def fit(self, X, y=None, **fit_params):
        self.vec_size = len(X[0])
        self.tfidf.fit(map(lambda x: '\n\n'.join(x), X))
        return self
    
    def transform(self, X, **transform_params):
        tX = map(lambda x: self.tfidf.transform(x).toarray().flatten(), X)
        return tX

    def get_feature_names(self):
        feature_arr = map(lambda i: self.tfidf.get_feature_names(), range(self.vec_size))
        return np.array(feature_arr).flatten()



class GetEncountersFeaturesTransformer(TransformerMixin):
    """Returns a feature vector for each empi from the encounters history
    of that patient.  Check below for details as it may change, but in general
    the feature vector will have two parts: (a) small feature vector for each
    of the encounters before the operation (with max_encounters as the max);
    (b) a series of features derived from the overall encounter history for the
    given patient (such as averages, sums, counts, maximums, etc.).
    Setting only_general flag to True returns only features in (b)."""
    def __init__(self, max_encounters, only_general=False):
        self.max_encounters = max_encounters
        self.only_general = only_general

    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_encounters_features, X)
        return transformed_X

    def get_feature_names(self):
        names = []
        for i in range(self.max_encounters):
            names.append('Inpatient_Outpatient_Enc_' + str(i))
            names.append('LOS_Enc_' + str(i))
            names.append('Num_Extra_Diagnoses_Enc_' + str(i))
        names.append('Enc_Inpatient_Ratio')
        names.append('Enc_Average_LOS')
        names.append('Enc_Average_Extra_Diagnoses')
        return np.array(names)
    
    def get_encounters_features(self, empi):
        encounters = structured_data_extractor.get_encounters(empi)
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        operation_index = 0
        for enc in encounters:
            if enc[0] < operation_date:
                operation_index += 1
            else:
                break
        # only look at encounters before the operation
        encounters = encounters[:operation_index]
        features = []
        # INDIVIDUAL ENCOUNTER FEATURES (3 x max_encounters)
        num_tracked_encounters = min(self.max_encounters, len(encounters))
        # tracked_encounters below is sorted by increasing absolute time delta with operation date
        tracked_encounters = encounters[::-1][:num_tracked_encounters]
        inpatients = 0
        total_LOS = 0
        total_extra_diagnoses = 0
        for enc in tracked_encounters:
            # INDIVIDUAL FEATURE 1 - Inpatient vs. Outpatient
            if enc[1] == 'Inpatient':
                features.append(1)
                inpatients += 1
            else:
                features.append(0)
            # INDIVIDUAL FEATURE 2 - Length of Stay
            if enc[3] > 1:
                features.append(enc[3])
                total_LOS += enc[3]
            else:
                features.append(0)
            # INDIVIDUAL FEATURE 3 - Number of Extra Diagnoses
            features.append(enc[4])
            total_extra_diagnoses += enc[4]
        # fill in remaining vector space with zeros to make vector size = 3 x max_encounters
        if num_tracked_encounters < self.max_encounters:
            delta = self.max_encounters - num_tracked_encounters
            for i in range(delta):
                for j in range(3):
                    features.append(0)
        # OVERALL ENCOUNTERS FEATURES (3)
        # OVERALL FEATURE 1 - Inpatient Ratio
        if len(tracked_encounters) > 0:
            features.append(inpatients / len(tracked_encounters))
        else:
            features.append(0)
        # OVERALL FEATURE 2 - Average LOS
        if inpatients > 0:
            features.append(total_LOS / inpatients)
        else:
            features.append(0)
        # OVERALL FEATURE 3 - Average Extra Diagnoses
        if len(tracked_encounters) > 0:
            features.append(total_extra_diagnoses / len(tracked_encounters))
        else:
            features.append(0)
        if self.only_general:
            features = features[-3:]
        return np.array(features) 

class GetLabsCountsDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary of lab test names to a count
    of the amount of times that patient has received that test before the
    operation. Output should then be fed into DictVectorizer."""
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_labs_counts, X)
        return transformed_X
    
    def get_labs_counts(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        return structured_data_extractor.get_labs_before_date(empi, operation_date)[0]

class GetLabsLowCountsDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary of lab test names to a count
    of the amount of times that patient has received that test before the
    operation and the test value was low. Output should then be fed into DictVectorizer."""
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_low_counts, X)
        return transformed_X
    
    def get_low_counts(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        return structured_data_extractor.get_labs_before_date(empi, operation_date)[1]

class GetLabsHighCountsDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary of lab test names to a count
    of the amount of times that patient has received that test before the
    operation and the test value was high. Output should then be fed into DictVectorizer."""
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_high_counts, X)
        return transformed_X
    
    def get_high_counts(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        return structured_data_extractor.get_labs_before_date(empi, operation_date)[2]

class GetLabsLatestHighDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary of lab test names to a boolean
    indicating if the test value was high the last time the patient received
    that test (before the procedue). Output should then be fed into DictVectorizer."""
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_labs_latest_high, X)
        return transformed_X
    
    def get_labs_latest_high(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        labs_latest = structured_data_extractor.get_labs_before_date(empi, operation_date)[3]
        labs_latest_high = {}
        for lab in labs_latest:
            if labs_latest[lab][1] == 'H':
                labs_latest_high[lab] = 1
            else:
                labs_latest_high[lab] = 0
        return labs_latest_high

class GetLabsLatestLowDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary of lab test names to a boolean
    indicating if the test value was low the last time the patient received
    that test (before the procedue). Output should then be fed into DictVectorizer.""" 
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_labs_latest_low, X)
        return transformed_X
    
    def get_labs_latest_low(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        labs_latest = structured_data_extractor.get_labs_before_date(empi, operation_date)[3]
        labs_latest_low = {}
        for lab in labs_latest:
            if labs_latest[lab][1] == 'L':
                labs_latest_low[lab] = 1
            else:
                labs_latest_low[lab] = 0
        return labs_latest_low

class GetLabsHistoryDictTransformer(TransformerMixin):
    """For each empi, will return a dictionary where keys are a concatenation of
    the lab test name, H(igh) or L(ow), and the time threshold looking back (i.e. "NA_H_6"
    would be testing for High results on the NA test around 6 months before prcedure).  
    The value is just a boolean indicating if this result was high (for H) or low (for L).
    Output should then be fed into DictVectorizer.""" 
    def __init__(self, time_thresholds_months):
        self.time_thresholds_months = time_thresholds_months

    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_labs_history, X)
        return transformed_X
    
    def get_labs_history(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        lab_history = structured_data_extractor.get_lab_history_before_date(empi, operation_date, self.time_thresholds_months)
        lab_history_transformed = {}
        for lab in lab_history:
            for i in range(len(self.time_thresholds_months)):
                lab_history_transformed[lab + '_H_' + str(self.time_thresholds_months[i])] = 1 if lab_history[lab][i] == 'H' else 0
                lab_history_transformed[lab + '_L_' + str(self.time_thresholds_months[i])] = 1 if lab_history[lab][i] == 'L' else 0
        return lab_history_transformed

class GetLatestLabValuesTransformer(TransformerMixin):
    def fit(self, X, y=None, **fit_params):
        return self

    def transform(self, X, **transform_params):
        transformed_X = map(self.get_latest_lab_values, X)
        return transformed_X
    
    def get_latest_lab_values(self, empi):
        person = loader.get_patient_by_EMPI(empi)
        operation_date = build_graphs.get_operation_date(person)
        latest_labs = structured_data_extractor.get_recent_lab_values(empi, operation_date) 
        latest_lab_values = {}
        for lab in latest_labs:
            if latest_labs[lab][1]:
                try:
                    latest_lab_values[lab] = float(latest_labs[lab][1])
                except:
                    latest_lab_values[lab] = latest_labs[lab][1]
        return latest_lab_values           
 
if __name__ == '__main__':
    labsTransformer = GetLatestLabValuesTransformer()
    labs = labsTransformer.get_latest_lab_values("FAKE_EMPI_648")
    for lab in labs:
        print(lab + ": " + str(labs[lab]))
