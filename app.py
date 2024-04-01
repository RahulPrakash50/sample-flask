
from flask import Flask, request, jsonify
from flask_cors import CORS
import math


app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello from Flask!'
CORS(app)

#helper function to convert utility data to the correct units
def convert_to_correct_units(electricity, electricity_units, natural_gas, natural_gas_units, steam, steam_units, fuel_oil_2, fuel_oil_2_units, fuel_oil_4, fuel_oil_4_units):
    #format the values to be in the following units: kWh, kBtu, kBtu, kBtu, kBtu
    if electricity_units == 'kBtu':
        electricity = electricity / 3.412

    if natural_gas_units == 'therms':
        natural_gas = natural_gas * 100

    if steam_units == 'Mlbs':
        steam = steam * 1194000
    
    if fuel_oil_2_units == 'gallons':
        fuel_oil_2 = fuel_oil_2 * 138
    
    if fuel_oil_4_units == 'gallons':
        fuel_oil_4 = fuel_oil_4 * 146

    return electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4

#create a helper function to format the occupancy data
def format_occupancy_data(primaryOccupancy, primary_gfa, primary_gfa_units, additionalOccupancies):
    #create an array of all occupancies including the primary occupancy with its square footage
    all_occupancies = []
    if primary_gfa_units == 'sqm':
        primary_square_footage = primary_gfa * 10.7639
    else: 
        primary_square_footage = primary_gfa
    
    all_occupancies.append({"occupancy": primaryOccupancy, "square_footage": primary_square_footage})

    for occupancy in additionalOccupancies:
        if occupancy['gfa_units'] == 'sqm':
            square_footage = occupancy['gfa'] * 10.7639
        else: 
            square_footage = occupancy['gfa']
        all_occupancies.append({"occupancy": occupancy['additional_occupancy_type'], "square_footage": square_footage})
    return all_occupancies

#calculate penalties
@app.route('/calculate-penalties', methods=['POST'])
def calculate_penalties():
    #get the data from the request
    data = request.json

    #extract data from the request
    jurisdiction = data.get('jurisdiction')
    primary_occupancy = data.get('primaryOccupancy')
    primary_gfa = float(data.get('primary_gfa'))
    primary_gfa_units = data.get('primary_gfa_units')
    additionalOccupancies = data.get('additionalOccupancies')

    #format the occupancy data
    all_occupancies = format_occupancy_data(primary_occupancy, primary_gfa, primary_gfa_units, additionalOccupancies)

    #extract utility data from the request
    electricity = data.get('electricity')
    electricity_units = data.get('electricity_units')
    natural_gas = data.get('naturalGas')
    natural_gas_units = data.get('naturalGas_units')
    steam = data.get('steam')
    steam_units = data.get('steam_units')
    fuel_oil_2 = data.get('fuel_oil_2')
    fuel_oil_2_units = data.get('fuel_oil_2_units')
    fuel_oil_4 = data.get('fuel_oil_4')
    fuel_oil_4_units = data.get('fuel_oil_2_units')

    #convert utility data to the correct units
    electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4 = convert_to_correct_units(electricity, electricity_units, natural_gas, natural_gas_units, steam, steam_units, fuel_oil_2, fuel_oil_2_units, fuel_oil_4, fuel_oil_4_units)

    # Mapping jurisdictions to their corresponding functions
    jurisdiction_functions = {
        'new-york-city': LL97_Calculator,
        'boston': BERDO_Calculator,
        'colorado': Colorado_Calculator,
    }

    # Retrieving the function based on jurisdiction, if none found, assign a lambda that returns an error message
    calculate_function = jurisdiction_functions.get(jurisdiction, lambda _: "Jurisdiction not handled")

    # Call the function and pass all data
    penalties, total_emissions, target_emissions = calculate_function(data, all_occupancies, electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4)
    
    #format the results as a json object and return it
    results_data = {
            'penalties': penalties,
            'total_emissions': total_emissions,
            'target_emissions': target_emissions,
            'building_data' : data,
    }
    return jsonify(results_data)


def LL97_Calculator(data, all_occupancies, electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4):

    penalties = {} #dictionary of penalties with year as key and penalty as value
    total_emissions = {} #dictionary of total emissions with year as key and total emissions as value
    target_emissions = {} #dictionary of target emissions with year as key and target emissions as value

    #GHG emissions factors used to calculate total emissions limits for each occupancy classification
    #in tCO2e/sqft
    limits_2024_2029 = {
    "Group A (Assembly)": 0.01074, "Group B (Business)": 0.00846, "Group B (Healthcare)": 0.02381, "Group E (Education)": 0.00758,
    "Group F (Factory / Industrial)": 0.00574, "Group H (High Hazard)": 0.02381, "Group I-1 (Institutional)": 0.01138,
    "Group I-2 (Institutional)": 0.02381, "Group I-3 (Institutional)": 0.02381, "Group I-4 (Institutional)": 0.00758,
    "Group M (Mercantile)": 0.01181, "Group R-1 (Residential)": 0.00987, "Group R-2 (Residential)": 0.00675, "Group S (Storage)": 0.00426,
    "Group U (Utility)": 0.00426
    }

    limits_2030_2034 = {
    "Group A (Assembly)": 0.00420, "Group B (Business)": 0.00453, "Group B (Healthcare)": 0.01193, "Group E (Education)": 0.00344,
    "Group F (Factory / Industrial)": 0.00167, "Group H (High Hazard)": 0.01193, "Group I-1 (Institutional)": 0.00598,
    "Group I-2 (Institutional)": 0.01193, "Group I-3 (Institutional)": 0.01193, "Group I-4 (Institutional)": 0.00344,
    "Group M (Mercantile)": 0.00403, "Group R-1 (Residential)": 0.00526, "Group R-2 (Residential)": 0.00407, "Group S (Storage)": 0.00110,
    "Group U (Utility)": 0.00110
    }
    
    #for each occupancy classification in the building, find the limit per square foot and multiply by the square footage.
    #add the total limits for each occupancy classification to get the total limit for the building for 2024-2029 and 2030-2034
    total_limit_2024_2029 = 0
    total_limit_2030_2034 = 0
    square_footage = 0
    for occupancy in all_occupancies:
        limit_2024_2029 = limits_2024_2029[occupancy['occupancy']]
        limit_2030_2034 = limits_2030_2034[occupancy['occupancy']]
        total_limit_2024_2029 += occupancy['square_footage'] * limit_2024_2029
        total_limit_2030_2034 += occupancy['square_footage'] * limit_2030_2034
        square_footage += occupancy['square_footage']

    #set the target emissions for each year from 2025-2034
    for year in range(2025, 2035):
        if year < 2030:
            target_emissions[year] = total_limit_2024_2029
        else:
            target_emissions[year] = total_limit_2030_2034

    #emissions rates (converts the units to tCO2e)
    Electricity_Rate = 0.000288962 #tCO2e/kWh
    Natural_gas_Rate = 0.00005311 #tCO2e/kBtu
    Steam_Rate = 0.00004493 #tCO2e/kBtu
    two_fuel_oil_Rate = 0.00007421 #tCO2e/kBtu
    four_fuel_oil_Rate = 0.00007529 #tCO2e/kBtu

    #calculate the total emissions (tCO2e)
    building_total_emissions = (electricity * Electricity_Rate) + (natural_gas * Natural_gas_Rate) + (steam * Steam_Rate) + (fuel_oil_2 * two_fuel_oil_Rate) + (fuel_oil_4 * four_fuel_oil_Rate)

    #add the total emissions to the total_emissions dictionary for year 2023
    total_emissions[2023] = building_total_emissions

    #classify the building as compliant or non-compliant for both 2024-2029 and 2030-2034
    if (building_total_emissions - total_limit_2024_2029) > 0:
        compliant_24 = 'No'
    else:
        compliant_24 = 'Yes'

    if (building_total_emissions - total_limit_2030_2034) > 0:
        compliant_30 = 'No'
    else:
        compliant_30 = 'Yes'

    #calculate the penalties for 2024-2029 and 2030-2034
    if compliant_24 == 'Yes' or square_footage < 25000:
        penalty_24 = 0
    else:
        penalty_24 = (math.floor(building_total_emissions - total_limit_2024_2029)) * 268

    if compliant_30 == 'Yes' or square_footage < 25000:
        penalty_30 = 0
    else:
        penalty_30 = (math.floor(building_total_emissions - total_limit_2030_2034)) * 268

    #populate the penalties dictionary with the penalties for 2024-2029 and 2030-2034
    for year in range(2025, 2035):
        if year < 2030:
            penalties[year] = penalty_24
        else:
            penalties[year] = penalty_30

    return penalties, total_emissions, target_emissions


def BERDO_Calculator(data, all_occupancies, electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4):

    number_of_units = int(data.get('number_of_units'))

    #GHG emissions factors used to calculate total emissions limits for each occupancy classification
    #in mtCO2e/sqft    
    limits_2025_2029 = {
    "Group A (Assembly)": 0.0078, "Group C (College/University)": 0.0102, "Group E (Education)": 0.0039, "Group F (Food Sales & Services)": 0.0174,
    "Group H (Healthcare)": 0.0154, "Group L (Lodging)": 0.0058, "Group M (Manufacturing / Industrial)": 0.0239,
    "Group M (Multifamily Housing)": 0.0041, "Group O (Office)": 0.0053, "Group R (Retail)": 0.0071,
    "Group S (Services)": 0.0075, "Group S (Storage)": 0.0054, "Group T (Technology / Science)": 0.0192
    }

    limits_2030_2034 = {
    "Group A (Assembly)": 0.0046, "Group C (College/University)": 0.0053, "Group E (Education)": 0.0024, "Group F (Food Sales & Services)": 0.0109,
    "Group H (Healthcare)": 0.0100, "Group L (Lodging)": 0.0037, "Group M (Manufacturing / Industrial)": 0.0153,
    "Group M (Multifamily Housing)": 0.0024, "Group O (Office)": 0.0032, "Group R (Retail)": 0.0034,
    "Group S (Services)": 0.0045, "Group S (Storage)": 0.0028, "Group T (Technology / Science)": 0.0111
    }

    penalties = {} #dictionary of penalties with year as key and penalty as value
    total_emissions = {} #dictionary of total emissions with year as key and total emissions as value
    target_emissions = {} #dictionary of target emissions with year as key and target emissions as value

    #for each occupancy classification in the building, find the limit per square foot and multiply by the square footage.
    #add the total limits for each occupancy classification to get the total limit for the building for 2025-2029 and 2030-2034
    building_total_limit_2025_2029 = 0
    building_total_limit_2030_2034 = 0
    square_footage = 0
    for occupancy in all_occupancies:
        limit_2025_2029 = limits_2025_2029[occupancy['occupancy']]
        limit_2030_2034 = limits_2030_2034[occupancy['occupancy']]
        building_total_limit_2025_2029 += occupancy['square_footage'] * limit_2025_2029
        building_total_limit_2030_2034 += occupancy['square_footage'] * limit_2030_2034
        square_footage += occupancy['square_footage']

    #set the target emissions for each year from 2025-2034
    for year in range(2025, 2035):
        if year < 2030:
            target_emissions[year] = building_total_limit_2025_2029 * 1.102 #convert to tons
        else:
            target_emissions[year] = building_total_limit_2030_2034 * 1.102 #convert to tons


    #emissions rates (converts the units to tCO2e)
    Electricity_Rate = 0.000288962
    Steam_Rate = 0.00004493
    Natural_gas_Rate = 0.00005311
    two_fuel_oil_Rate = 0.00007421
    four_fuel_oil_Rate = 0.00007529

    #calculate the total emissions in tons
    building_total_emissions = (natural_gas * Natural_gas_Rate) + (fuel_oil_2 * two_fuel_oil_Rate) + (fuel_oil_4 * four_fuel_oil_Rate) + (electricity * Electricity_Rate) + (steam * Steam_Rate)
    #add the total emissions to the total_emissions dictionary for year 2023
    total_emissions[2023] = building_total_emissions

    #calculate the total emissions in metric tons
    building_total_emisisons_metric_tons = building_total_emissions / 1.102

    #alternative compliance payments: $234 per metric ton of CO2e above the limit
    acp_25 = 0
    acp_30 = 0

    #classify the building as compliant or non-compliant for both 2025-2029 and 2030-2034
    if ((building_total_emisisons_metric_tons - building_total_limit_2025_2029) > 0) and (number_of_units >= 35 or square_footage >= 35000):
        #calculate the alternative compliance payment
        acp_25 = (building_total_emisisons_metric_tons - building_total_limit_2025_2029) * 234
        penalty_25 = acp_25
    else:
        penalty_25 = 0

    if ((building_total_emisisons_metric_tons - building_total_limit_2030_2034) > 0) and (number_of_units >= 15 or square_footage >= 20000):
        #calculate the alternative compliance payment
        acp_30 = (building_total_emisisons_metric_tons - building_total_limit_2030_2034) * 234
        penalty_30 = acp_30
    else:
        penalty_30 = 0

    #populate the penalties dictionary with the penalties for 2025-2029 and 2030-2034
    for year in range(2025, 2035):
        if year < 2030 and year >= 2025:
            penalties[year] = penalty_25
        if year >= 2030:
            penalties[year] = penalty_30

    return penalties, total_emissions, target_emissions


def Colorado_Calculator(data, all_occupancies, electricity, natural_gas, steam, fuel_oil_2, fuel_oil_4):

    #using all occupancies, calculate square footage
    square_footage = 0
    for occupancy in all_occupancies:
            square_footage += occupancy['square_footage']
    
    property_types = [
    "College/University", "Courthouse", "Food Service", "Hospital (General Medical & Surgical)",
    "Hotel", "K-12 School", "Medical Office", "Multifamily Housing", "Office"]

    #EUI in kBTU/SF
    _2026_site_EUI = [74.1, 66.8, 244.3, 217.6, 64.3, 56.9, 76.7, 50.6, 57.2]
    _2030_site_EUI = [58.3, 53.6, 195.9, 172, 54.3, 49.1, 64.9, 42.1, 46.9]

    #GHGi in kgCO2e/SF
    _2026_GHG_intensity = [4.6, 4.1, 15.2, 13.5, 4.0, 3.5, 4.8, 3.1, 3.5]
    _2030_GHG_intensity = [2.6, 2.4, 8.7, 7.7, 2.4, 2.2, 2.9, 1.9, 2.1]

    limits_dict = {}
    for i, property_type in enumerate(property_types):
        limits_dict[property_type] = {
            2026: {"GHG": _2026_GHG_intensity[i], "EUI": _2026_site_EUI[i]},
            2030: {"GHG": _2030_GHG_intensity[i], "EUI": _2030_site_EUI[i]},
        }

    penalties = {} #dictionary of penalties with year as key and penalty as value
    total_emissions = {} #dictionary of total emissions with year as key and total emissions as value
    target_emissions = {} #dictionary of target emissions with year as key and target emissions as value

    #read in emissions data
    electricity_kBtu = electricity * 3.412


    #emissions rates
    Electricity_Rate = 0.000288962
    Steam_Rate = 0.00004493
    Natural_gas_Rate = 0.00005311
    two_fuel_oil_Rate = 0.00007421
    four_fuel_oil_Rate = 0.00007529

    #calculate the total emissions
    building_total_emissions = (natural_gas * Natural_gas_Rate) + (fuel_oil_2 * two_fuel_oil_Rate) + (fuel_oil_4 * four_fuel_oil_Rate) + (electricity * Electricity_Rate) + (steam * Steam_Rate)
    #add the total emissions to the total_emissions dictionary for year 2023
    total_emissions[2023] = building_total_emissions

    #calculate building eui (kBtu/sqft)
    building_eui = (electricity_kBtu + natural_gas + steam + fuel_oil_2 + fuel_oil_4) / square_footage

    #calculate building ghgi (kgCO2e/sqft)
    building_ghgi = (building_total_emissions / square_footage) * 1000

    #buildings with less than 50,000 square feet are exempt from the BPS
    if square_footage < 50000:
        for year in range(2025, 2035):
            penalties[year] = 0
            target_emissions[year] = building_total_emissions
        return penalties, total_emissions, target_emissions

    #penalty rate per month
    penalty_rate = 5000

    #calculate limit_eui and limit_ghg for 2026-2029 and 2030-2034
    #find each occupancy classification's ghgi and eui limits and calculate the total ghgi and eui limits for the building for 2026-2029 and 2030-2034
    #the eui limit is a weighted average of the eui limits for each occupancy classification based on the square footage of each occupancy classification
    limit_ghgi_2026_2029 = 0
    limit_ghgi_2030_2034 = 0
    limit_eui_2026_2029 = 0
    limit_eui_2030_2034 = 0
    for occupancy in all_occupancies:
        limit_2026 = limits_dict[occupancy['occupancy']][2026]
        limit_2030 = limits_dict[occupancy['occupancy']][2030]
        limit_ghgi_2026_2029 += (occupancy['square_footage'] * limit_2026['GHG'])
        limit_ghgi_2030_2034 += (occupancy['square_footage'] * limit_2030['GHG']) 
        limit_eui_2026_2029 += (occupancy['square_footage'] * limit_2026['EUI'])
        limit_eui_2030_2034 += (occupancy['square_footage'] * limit_2030['EUI'])
    
    limit_ghgi_2026_2029 = limit_ghgi_2026_2029 / square_footage
    limit_ghgi_2030_2034 = limit_ghgi_2030_2034 / square_footage
    limit_eui_2026_2029 = limit_eui_2026_2029 / square_footage
    limit_eui_2030_2034 = limit_eui_2030_2034 / square_footage

    for year in range(2025, 2035):
    # Default penalty for years before 2026
        if year < 2026:
            penalties[year] = 0
            # limit_ghgi = limits_dict[property_occupancy][2026]['GHG']
            target_emissions[year] = limit_ghgi_2026_2029 * square_footage / 1000
            continue

        # Determine the appropriate limits based on the year
        if year < 2030:
            limit_eui = limit_eui_2026_2029
            limit_ghgi = limit_ghgi_2026_2029
        else:
            limit_eui = limit_eui_2030_2034
            limit_ghgi = limit_ghgi_2030_2034

        # Check if the building is non-compliant for EUI or GHGI
        if building_eui > limit_eui or building_ghgi > limit_ghgi:
            penalties[year] = penalty_rate * 12
        else:
            penalties[year] = 0  # This line ensures penalties are explicitly set to 0 for compliant years

        target_emissions[year] = limit_ghgi *square_footage / 1000

    return penalties, total_emissions, target_emissions

if __name__ == '__main__':
    app.run(debug=True, port = 5000)
