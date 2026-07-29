from django import template
from num2words import num2words
import math

register = template.Library()

@register.filter
def amount_in_words(amount):
    """
    Converts a decimal amount to words in English (e.g. 105.50 -> One hundred and five Taka and fifty Poisha).
    Since we don't have exact currency specifics, we'll keep it generic or assume Taka/Poisha for Bangladesh.
    Let's just output generic words without specific currency names if possible, 
    or use the standard num2words format.
    """
    if amount is None:
        return ""
        
    try:
        amount = float(amount)
        
        integer_part = math.floor(amount)
        fractional_part = int(round((amount - integer_part) * 100))
        
        main_words = num2words(integer_part)
        
        if fractional_part > 0:
            fraction_words = num2words(fractional_part)
            result = f"{main_words} Taka and {fraction_words} Poisha"
        else:
            result = f"{main_words} Taka"
            
        return result.replace("-", " ").title() + " Only"
    except (ValueError, TypeError):
        return ""
