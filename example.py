food = ""
spice = 0
sweet = 0
savor = 0
cuisine = "other"
meal = "other"
taste_profile = "5-5-5-American-Lunch"

def Taste_Checker(taste, food_data):
    points = 0
    temp_check = ""
    for char in taste:
        if char != '-':
            temp_check+=char
        else:
            

with open("formatted_menu_items.txt", "r", encoding="utf8") as file:
    content = file.read()
    temp_string = ""
    count = 0
    for char in content:
        if char != ':':
          temp_string+= char
          if char == '-':
            if count == 0:
                food = temp_string
            elif count == 1:
                spice = temp_string
            elif count == 2:
                sweet = temp_string
            elif count == 3:
                savor = temp_string
            elif count == 4:
                cuisine = temp_string
            else:
                meal = temp_string
            temp_string = ""
            count += 1
        else:
            Taste_Checker(taste_profile, temp_string)
            
       
        
