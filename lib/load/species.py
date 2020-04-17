""" read spcies
"""

import os
import chemkin_io
import automol
import autoparse.find as apf
import autofile
from lib.load import ptt
from lib.phydat import symm, eleclvl
from lib.reaction import rxnid
from lib.filesystem import read as fread
from lib.filesystem import inf as finf
from lib.filesystem import path as fpath
from lib.phydat import phycon


CSV_INP = 'inp/species.csv'
DAT_INP = 'inp/species.dat'
CLA_INP = 'inp/class.csv'


def build_run_spc_dct(spc_dct, run_obj_dct):
    """ Get a dictionary of requested species matching the PES_DCT format
    """
    spc_nums = run_obj_dct['spc']
    run_spc_lst = []
    for idx, spc in enumerate(spc_dct):
        if spc != 'global':
            if idx+1 in spc_nums:
                run_spc_lst.append((spc, run_obj_dct['spc'][idx+1]))

    # Build the run dct
    run_dct = {}
    run_dct['all'] = {
        'species': run_spc_lst,
        'reacs': [],
        'prods': []
    }

    return run_dct


def build_spc_dct(job_path, spc_type, check_stereo=False):
    """ Get a dictionary of all the input species
        indexed by InChi string
    """
    spc_csv_str = ptt.read_inp_str(job_path, CSV_INP)
    if spc_type == 'csv':
        spc_dct = csv_dct(spc_csv_str, check_stereo=check_stereo)
    else:
        raise NotImplementedError

    # Modify spc dct with params from the AMech file
    mod_spc_dct = modify_spc_dct(job_path, spc_dct)

    return mod_spc_dct


def csv_dct(spc_str, check_stereo):
    """ read the species file in a .csv format
    """
    # Read in the initial CSV information
    smi_dct = chemkin_io.parser.mechanism.spc_name_dct(spc_str, 'smiles')
    ich_dct = chemkin_io.parser.mechanism.spc_name_dct(spc_str, 'inchi')
    mul_dct = chemkin_io.parser.mechanism.spc_name_dct(spc_str, 'mult')
    chg_dct = chemkin_io.parser.mechanism.spc_name_dct(spc_str, 'charge')
    sens_dct = chemkin_io.parser.mechanism.spc_name_dct(spc_str, 'sens')

    # Print message detailing if stereochemistry is used
    print_check_stero_msg(check_stereo)

    # Rebuild with stereochemistry if possible
    if check_stereo:
        spc_str = 'name,SMILES,InChI,mult,charge,sens \n'
        for name in ich_dct:
            ich = ich_dct[name]
            smi = smi_dct[name]
            mul = mul_dct[name]
            chg = chg_dct[name]
            sens = sens_dct[name]
            if not automol.inchi.is_complete(ich):
                print('adding stereochemistry for {0}, {1}, {2}'.format(
                    name, smi, ich))
                # this returns a list of ichs w/ different possible stereo vals
                # for now just taking the first of these
                ich = automol.inchi.add_stereo(ich)
                ich = ich[-1]
                ich_dct[name] = ich
            spc_str += '{0},\'{1}\',\'{2}\',{3},{4},{5} \n'.format(
                name, smi, ich, mul, chg, sens)

        stereo_path = 'species_stereo.csv'
        with open(stereo_path, 'w') as stereo_csv_file:
            stereo_csv_file.write(spc_str)

    # Build the final dictionary
    spc_names = []
    spc_dct = {}
    for name in mul_dct:
        spc_dct[name] = {}
        spc_dct[name]['smi'] = smi_dct[name]
        if isinstance(ich_dct[name], str):
            spc_dct[name]['ich'] = ich_dct[name]
        elif isinstance(smi_dct[name], str):
            spc_dct[name]['ich'] = automol.smiles.inchi(smi_dct[name])
        else:
            print('No Inchi string for {}'.format(name))
            spc_dct[name]['ich'] = ''
        spc_dct[name]['chg'] = chg_dct[name]
        spc_dct[name]['mul'] = mul_dct[name]
        spc_names.append(name)

    return spc_dct


def read_spc_amech(job_path):
    """ Read an amech style input file for the species
    """

    # Read the AMech species string
    if os.path.exists(os.path.join(job_path, DAT_INP)):
        spc_amech_str = ptt.read_inp_str(job_path, DAT_INP)
    else:
        spc_amech_str = ''

    # Build the keyword dcts
    amech_dct = {}
    if spc_amech_str:
        # Read each of the species sections and build the dcts
        spc_sections = apf.all_captures(
            ptt.end_section_wname2('spc'), spc_amech_str)
        if spc_sections:
            # Get the global species section
            for section in spc_sections:
                if section[0] == 'global':
                    # Build the global species section
                    keyword_dct = ptt.build_keyword_dct(section[1])
                    amech_dct['global'] = keyword_dct
                else:
                    # Build each species dct to overwrite global dct
                    name = section[0]
                    keyword_dct = ptt.build_keyword_dct(section[1])
                    amech_dct[name] = keyword_dct

    return amech_dct


def modify_spc_dct(job_path, spc_dct):
    """ Modify the species dct using input from the additional AMech file
    """

    # Read in other dcts
    amech_dct = read_spc_amech(job_path)
    geom_dct = geometry_dictionary(job_path)

    # First loop for species defined in the csv file
    mod_spc_dct = {}
    for spc in spc_dct:
        # Set the ich and mult
        ich = spc_dct[spc]['ich']
        mul = spc_dct[spc]['mul']
        chg = spc_dct[spc]['chg']
        mod_spc_dct[spc] = {}
        mod_spc_dct[spc]['ich'] = ich
        mod_spc_dct[spc]['mul'] = mul
        mod_spc_dct[spc]['chg'] = chg

        # Add params from global dct in amech dct
        if 'global' in amech_dct:
            for key, val in amech_dct['global'].items():
                mod_spc_dct[spc][key] = val

        # Add/Reset the parameters from the species specific dct
        if spc in amech_dct:
            for key, val in amech_dct[spc].items():
                mod_spc_dct[spc][key] = val

    # Second loop for transtion states defined in species.dat
    for spc in amech_dct:
        if 'ts' in spc:
            mod_spc_dct[spc] = {}
            # Add params from global dct in amech dct
            if 'global' in amech_dct:
                for key, val in amech_dct['global'].items():
                    mod_spc_dct[spc][key] = val
            # Add the ts stuff
            mod_spc_dct[spc] = amech_dct[spc]

    # Add global to mod_spc_dct for other TS stuff later
    if 'global' in amech_dct:
        mod_spc_dct['global'] = amech_dct['global']

    # Final loop to add in things that are needed but could be missing
    for spc in mod_spc_dct:
        if spc != 'global':
            ich, mul = mod_spc_dct[spc]['ich'], mod_spc_dct[spc]['mul']
            if 'elec_levs' not in mod_spc_dct[spc]:
                if (ich, mul) in eleclvl.DCT:
                    mod_spc_dct[spc]['elec_levs'] = eleclvl.DCT[(ich, mul)]
                else:
                    mod_spc_dct[spc]['elec_levs'] = [[0.0, mul]]
            if 'sym' not in mod_spc_dct[spc]:
                if (ich, mul) in symm.DCT:
                    mod_spc_dct[spc]['sym'] = symm.DCT[(ich, mul)]

        # Add defaults here for now
        if 'hind_inc' not in mod_spc_dct[spc]:
            mod_spc_dct[spc]['hind_inc'] = 30.0
        if 'kickoff' not in mod_spc_dct[spc]:
            mod_spc_dct[spc]['kickoff'] = [0.1, False]
        if 'mc_nsamp' not in mod_spc_dct[spc]:
            mod_spc_dct[spc]['mc_nsamp'] = [1, 0, 0, 0, 0, False]
        if 'pst_params' not in mod_spc_dct[spc]:
            mod_spc_dct[spc]['pst_params'] = [1.0, 6]

        # Perform conversions as needed
        mod_spc_dct[spc]['hind_inc'] *= phycon.DEG2RAD
        # if 'ts' in spc:
        #     print(mod_spc_dct[spc]['hind_inc'])

        # Add geoms from geo dct (prob switch to amech file)
        if ich in geom_dct:
            mod_spc_dct[spc]['geo_obj'] = geom_dct[ich]

    return mod_spc_dct


def parse_rxn_class_file(job_path):
    """ Read the class dictionary
    """
 
    print('\nChecking if class.dat has been provided...')
    if os.path.exists(os.path.join(job_path, CLA_INP)):
        print('\nclass.dat found. Reading contents...')
        cla_str = ptt.read_inp_str(job_path, CLA_INP)
        cla_str = cla_str if cla_str else 'REACTION,RCLASS\nEND'
        cla_dct = chemkin_io.parser.mechanism.reac_class_dct(cla_str, 'class')
    else:
        print('\nNo class.dat found...')
        cla_dct = {}

    return cla_dct


def set_class_with_dct(cla_dct, rxn_name):
    """ set the class using the class dictionary
    """
    rxn_name = rxn_name_lst[idx]
    rxn_name_rev = '='.join(rname.split('=')[::-1])
    if rname in cla_dct:
        inp_class = cla_dct[rname]
        flip_rxn = False
    elif rname_rev in cla_dct:
        inp_class = cla_dct[rxn_name_rev]
        flip_rxn = True
    else:
        inp_class = None
        flip_rxn = False

    return inp_class, flip_rxn


def geometry_dictionary(job_path):
    """ read in dictionary of saved geometries
    """
    geom_path = os.path.join(job_path, 'data', 'geoms')
    geom_dct = {}
    for dir_path, _, file_names in os.walk(geom_path):
        for file_name in file_names:
            file_path = os.path.join(dir_path, file_name)
            if file_path.endswith('.xyz'):
                xyz_str = autofile.file.read_file(file_path)
                geo = automol.geom.from_xyz_string(xyz_str)
                ich = automol.geom.inchi(geo)
                if ich in geom_dct:
                    print('Warning: Dupilicate xyz geometry for ', ich)
                geom_dct[ich] = geo
    return geom_dct


def build_sadpt_dct(pes_idx, rxn_lst, thy_info, ini_thy_info,
                    run_inp_dct, spc_dct, cla_dct):
    """ build dct
    """
    run_prefix = run_inp_dct['run_prefix']
    save_prefix = run_inp_dct['save_prefix']
    kickoff = [0.1, False]

    print('\nTransition state prep')
    ts_dct = {}
    for chn_idx, rxn in enumerate(rxn_lst):

        # Initialize dictionary
        tsname = 'ts_{:g}_{:g}'.format(pes_idx, chn_idx+1)
        ts_dct[tsname] = {}

        # Grab the reactants and products
        reacs = rxn['reacs']
        prods = rxn['prods']

        # Check the class dct to see if we can set class
        # given_class, flip_rxn = set_class_with_dct(cla_dct, rxn_name)
        given_class = ''

        # Get the reaction info flipping if needed
        check_exo = True
        if check_exo and not given_class:
            reacs, prods = finf.assess_rxn_exo(
                reacs, prods, spc_dct, thy_info, ini_thy_info, save_prefix)
        print('\n {} for {} = {}'.format(
            tsname, '+'.join(reacs), '+'.join(prods)))

        # Set the info
        rxn_info = finf.rxn_info(reacs, prods, spc_dct)
        [rxn_ichs, rxn_chgs, rxn_muls, _] = rxn_info
        low_mul, high_mul, _, chg = finf.rxn_chg_mult(
            rxn_muls, rxn_chgs, ts_mul='low')
        rad_rad = rxnid.determine_rad_rad(rxn_muls)
        ts_mul = low_mul
        ts_dct[tsname].update(
            {'low_mul': low_mul,
             'high_mul': high_mul,
             'mul': ts_mul,
             'chg': chg,
             'rad_rad': rad_rad})
        ts_dct[tsname]['reacs'] = reacs
        ts_dct[tsname]['prods'] = prods

        # Generate rxn_fs from rxn_info stored in spc_dct
        [kickoff_size, kickoff_backward] = kickoff
        rct_zmas, prd_zmas, rct_cnf_save_fs, prd_cnf_save_fs = fread.get_zmas(
            reacs, prods, spc_dct,
            ini_thy_info, save_prefix, run_prefix, kickoff_size,
            kickoff_backward)
        ret = rxnid.ts_class(
            rct_zmas, prd_zmas, rad_rad,
            ts_mul, low_mul, high_mul,
            rct_cnf_save_fs, prd_cnf_save_fs, given_class)
        ret1, ret2 = ret

        if ret1:
            [_, _, dist_name, brk_name, _, _, _, _, update_guess] = ret1
            dct_keys = ['class', 'zma', 'dist_name', 'brk_name', 'grid',
                        'frm_bnd_key', 'brk_bnd_key',
                        'tors_names', 'update_guess']
            ts_dct[tsname].update(dict(zip(dct_keys, ret1)))
        else:
            ts_dct[tsname]['class'] = None
            ts_dct[tsname]['bkp_data'] = None
        ts_dct[tsname]['bkp_data'] = ret2 if ret2 else None
        ts_dct[tsname]['dist_info'] = [dist_name, 0., update_guess, brk_name]

        ts_dct[tsname]['ich'] = ''

        # Reaction fs for now
        rxn_run_fs, rxn_save_fs, rxn_run_path, rxn_save_path = fpath.get_rxn_fs(
            run_prefix, save_prefix, rxn_ichs, rxn_chgs, rxn_muls, ts_mul)
        ts_dct[tsname]['rxn_fs'] = [
            rxn_run_fs,
            rxn_save_fs,
            rxn_run_path,
            rxn_save_path]

    return ts_dct


def combine_sadpt_spc_dcts(sadpt_dct, spc_dct):
    """ Create a new dictionary that combines init spc_dct and sadpt dct
    """
    print('spc dct')
    for key in spc_dct:
        if 'ts' in key:
            print(spc_dct[key])
    print('sadpt dct')
    for key in sadpt_dct:
        if 'ts' in key:
            print(sadpt_dct[key])

    combined_dct = {}

    # Put all elements of spc_dct in combined dct that are NOT TSs
    for spc in spc_dct:
        if 'ts' not in spc:
            combined_dct[spc] = spc_dct[spc]

    # Now put in the TSs pulling info from everywhere
    for sadpt in sadpt_dct:

        # Put in stuff from the global dct
        combined_dct[sadpt] = {}
        if 'global' in spc_dct:
            for key, val in spc_dct['global'].items():
                combined_dct[sadpt][key] = val
            print('global')
            print(spc_dct['global']['hind_inc'])
            print(combined_dct['global']['hind_inc'])

        # Update any sadpt keywords if they are in the spc_dct from .dat file
        if sadpt in spc_dct:
            print('BOOOOOOOOOO')
            combined_dct[sadpt].update(spc_dct[sadpt])

        # Put in stuff from the sadpt_dct build
        for key, val in sadpt_dct[sadpt].items():
            if key not in combined_dct[sadpt]:
                combined_dct[sadpt][key] = val

        # Put in defaults if they were not defined
        if 'kickoff' not in combined_dct[sadpt]:
            combined_dct[sadpt]['kickoff'] = [0.1, False]
        if 'mc_nsamp' not in combined_dct[sadpt]:
            combined_dct[sadpt]['mc_nsamp'] = [True, 10, 1, 3, 50, 25]
        if 'irc_idxs' not in combined_dct[sadpt]:
            combined_dct[sadpt]['irc_idxs'] = [
                -10.0, -9.0, -8.0, -7.0, -6.0, -5.0, -4.0, -3.0,
                -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0,
                8.0, 9.0, 10.0]
        if 'pst_params' not in combined_dct[sadpt]:
            combined_dct[sadpt]['pst_params'] = [1.0, 6]

        # Perform conversions as needed
        # combined_dct[spc]['hind_inc'] *= phycon.DEG2RAD
   
    return combined_dct
    

# Print messages
def print_check_stero_msg(check_stereo):
    """ Print a message detailing whether stereo is being checked
    """
    if check_stereo:
        print('Species will be treated with stereochemistry.',
              'Checking and adding stereo.')
    else:
        print('Stereochemistry will be ignored')
