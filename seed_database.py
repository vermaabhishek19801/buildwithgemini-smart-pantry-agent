from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-9415c911d198"
DATABASE_ID = "smart-pantry-db"

def seed_data():
    db = firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
    
    # Seed Recipes
    recipes = [
        {
            "id": "spaghetti_carbonara",
            "name": "Spaghetti Carbonara",
            "cuisine": "Italian",
            "prep_time_minutes": 20,
            "ingredients": ["spaghetti", "eggs", "pancetta", "pecorino cheese", "black pepper"],
            "instructions": "Boil pasta. Fry pancetta until crispy. Beat eggs with grated cheese. Toss hot pasta with pancetta, then remove from heat and mix in egg mixture."
        },
        {
            "id": "chicken_tacos",
            "name": "Chicken Tacos",
            "cuisine": "Mexican",
            "prep_time_minutes": 15,
            "ingredients": ["chicken breast", "tortillas", "salsa", "cilantro", "lime"],
            "instructions": "Season and grill chicken breast. Slice into strips. Warm tortillas and assemble tacos with chicken, salsa, cilantro, and a squeeze of lime."
        },
        {
            "id": "avocado_toast",
            "name": "Avocado Toast",
            "cuisine": "American",
            "prep_time_minutes": 5,
            "ingredients": ["bread", "avocado", "salt", "red pepper flakes", "olive oil"],
            "instructions": "Toast bread slices. Mash fresh avocado with salt and olive oil. Spread onto toast and garnish with red pepper flakes."
        }
    ]

    for recipe in recipes:
        recipe_id = recipe.pop("id")
        db.collection("recipes").document(recipe_id).set(recipe)
        print(f"Seeded recipe: {recipe_id}")

    # Seed Pantry Items
    pantry_items = [
        {"id": "spaghetti", "item_name": "Spaghetti", "quantity": "500g", "category": "Pantry"},
        {"id": "eggs", "item_name": "Eggs", "quantity": "12 pcs", "category": "Refrigerated"},
        {"id": "chicken_breast", "item_name": "Chicken Breast", "quantity": "1 lb", "category": "Refrigerated"},
        {"id": "tortillas", "item_name": "Tortillas", "quantity": "8 pcs", "category": "Pantry"},
        {"id": "avocado", "item_name": "Avocado", "quantity": "2 pcs", "category": "Produce"}
    ]

    for item in pantry_items:
        item_id = item.pop("id")
        db.collection("pantry").document(item_id).set(item)
        print(f"Seeded pantry item: {item_id}")

if __name__ == "__main__":
    seed_data()
