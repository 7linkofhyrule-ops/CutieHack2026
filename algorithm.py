food = ""
spice = 0
sweet = 0
savor = 0
cuisine = ""
meal = ""
taste_profile = "0-2-7-italian-Lunch"
options=[]
biggest=0





def Taste_Checker(taste, food_data,biggest):
    i = 0
    points=0
    temp_check = ""
    for char in taste:
        if char != ('-'):
            temp_check+=char
        else:
            i+=1
            if i == 1:
              if abs(int(temp_check) - int(spice)) < 3:
                points +=1
            elif i ==2:
                if abs(int(temp_check) - int(sweet)) < 3:
                    points+=1
            elif i == 3:
                if abs(int(temp_check) - int(savor)) < 3:
                    points+=1
            elif i == 4:
                if temp_check == cuisine:
                    points+=1 
            elif i ==5:
                if meal == temp_check:
                    points+=10
                    # 10 to distinguish if we have it a the right time.
            temp_check = ""
    if points >= biggest:
        options.insert(0, food)
        options.insert(0, points)
        biggest = points
    else:
       options.append(points)
       options.append(food)
    return biggest
    
    

with open("formatted_menu_items.txt", "r", encoding="utf8") as file:
    content = file.read()
    temp_string = ""
    count = 0
    for char in content:
        if char != ':':
          if char != '-':
              temp_string+= char
          elif char == '-':
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
            temp_string = ""
            biggest = Taste_Checker(taste_profile, temp_string, biggest)
            count = 0
            
    print("I would reccomend: ")
    for i, item in enumerate(options):
        if isinstance(item, int):
          if item >= biggest:
              print(options[i+1])
              
        
