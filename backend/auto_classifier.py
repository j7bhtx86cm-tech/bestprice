"""
Автоклассификатор товаров BestPrice v12

Классифицирует товары по названию в категории super_class.
"""

import re
from typing import Optional, Tuple

# Правила классификации: (regex_pattern, super_class)
# Порядок важен - более специфичные правила первыми
CLASSIFICATION_RULES = [
    # === МОРЕПРОДУКТЫ ===
    # ВАЖНО: Икра ПЕРЕД лосось/горбуша, т.к. "икра лососевая" должна быть caviar, не salmon!
    (r'\b(икра|caviar|roe)(?!.*кабачк)(?!.*баклажан)', 'seafood.caviar'),
    (r'\b(креветк|shrimp|гаммарус)', 'seafood.shrimp'),
    (r'\b(кальмар|squid)', 'seafood.squid'),
    (r'\b(мидии|mussel)', 'seafood.mussels'),
    (r'\b(осьминог|octopus)', 'seafood.octopus'),
    (r'\b(краб|crab)', 'seafood.crab'),
    (r'\b(устриц|oyster)', 'seafood.oyster'),
    (r'\b(лосось|лосос|сёмга|семга|salmon)(?!.*икр)', 'seafood.salmon'),
    (r'\b(форель|trout)', 'seafood.trout'),
    (r'\b(тунец|tuna)', 'seafood.tuna'),
    (r'\b(треска|cod)', 'seafood.cod'),
    (r'\b(судак|pike.*perch)', 'seafood.pike_perch'),
    (r'\b(окун|perch)', 'seafood.perch'),
    (r'\b(карп|carp)', 'seafood.carp'),
    (r'\b(сельд|селёд|herring)', 'seafood.herring'),
    (r'\b(скумбри|mackerel)', 'seafood.mackerel'),
    (r'\b(морск.*коктейль|seafood.*mix)', 'seafood.mix'),
    (r'\b(чука|водоросл|seaweed|нори|wakame)', 'seafood.seaweed'),
    (r'\b(рыб|fish|филе.*рыб)', 'seafood.fish'),
    (r'\b(морепродукт)', 'seafood.mix'),
    (r'\b(минтай|pollock)', 'seafood.pollock'),
    (r'\b(горбуш|pink.*salmon)(?!.*икр)', 'seafood.salmon'),
    (r'\b(кета|chum)', 'seafood.salmon'),
    (r'\b(нерка|sockeye)', 'seafood.salmon'),
    (r'\b(палтус|halibut)', 'seafood.halibut'),
    (r'\b(камбал|flounder)', 'seafood.flounder'),
    (r'\b(дорад|dorado)', 'seafood.dorado'),
    (r'\b(сибас|seabass)', 'seafood.seabass'),
    (r'\b(тилапи|tilapia)', 'seafood.tilapia'),
    (r'\b(пангасиус|pangasius)', 'seafood.pangasius'),
    (r'\b(сардин|sardine)', 'seafood.sardine'),
    (r'\b(анчоус|anchovy)', 'seafood.anchovy'),
    
    # === МЯСО ===
    (r'\b(курин|куриц|курица|цыпл|chicken|бройлер)', 'meat.chicken'),
    (r'\b(индейк|индюш|turkey)', 'meat.turkey'),
    (r'\b(утк|duck)', 'meat.duck'),
    (r'\b(гус|goose)', 'meat.goose'),
    (r'\b(говядин|говяж|beef|бычок)', 'meat.beef'),
    (r'\b(свинин|свин|pork)', 'meat.pork'),
    (r'\b(баранин|баран|lamb|mutton)', 'meat.lamb'),
    (r'\b(телятин|телячь|veal)', 'meat.veal'),
    (r'\b(кролик|rabbit)', 'meat.rabbit'),
    (r'\b(оленин|venison)', 'meat.venison'),
    (r'\b(фарш|minced|рублен)', 'meat.minced'),
    (r'\b(колбас|sausage)', 'meat.sausage'),
    (r'\b(сосиск|frankfurter)', 'meat.sausage'),
    (r'\b(ветчин|ham)', 'meat.ham'),
    (r'\b(бекон|bacon)', 'meat.bacon'),
    (r'\b(салями|salami)', 'meat.salami'),
    (r'\b(шпик|сало|lard)', 'meat.lard'),
    (r'\b(паштет|pate)', 'meat.pate'),
    (r'\b(субпродукт|печен|сердц|язык|почк|offal|liver|heart)', 'meat.offal'),
    (r'\b(стейк|steak)', 'meat.steak'),
    (r'\b(филе.*кур|грудк.*кур|бедр.*кур)', 'meat.chicken'),
    (r'\b(окорок|ham)', 'meat.ham'),
    (r'\b(карбонад|карбонат)', 'meat.pork'),
    (r'\b(буженин)', 'meat.pork'),
    (r'\b(шашлык|kebab)', 'meat.kebab'),
    (r'\b(котлет|cutlet|биточ)', 'meat.cutlet'),
    (r'\b(пельмен|dumpling)', 'meat.dumplings'),
    (r'\b(манты|manti)', 'meat.dumplings'),
    (r'\b(хинкал)', 'meat.dumplings'),
    
    # === МОЛОЧНЫЕ ПРОДУКТЫ ===
    (r'\b(молок|milk)(?!.*кокос)(?!.*соев)(?!.*рис)(?!.*овс)(?!.*миндал)', 'dairy.milk'),
    (r'\b(сыр|cheese)(?!.*плавл)(?!.*творож)', 'dairy.cheese'),
    (r'\b(сыр.*плавл|плавл.*сыр)', 'dairy.cheese_processed'),
    (r'\b(творог|творож|curd|cottage)', 'dairy.cottage_cheese'),
    (r'\b(сметан|sour.*cream)', 'dairy.sour_cream'),
    (r'\b(кефир|kefir)', 'dairy.kefir'),
    (r'\b(йогурт|yogurt|yoghurt)', 'dairy.yogurt'),
    (r'\b(сливк|cream)(?!.*масл)(?!.*морож)', 'dairy.cream'),
    (r'\b(масло.*сливоч|сливоч.*масло|butter)', 'dairy.butter'),
    (r'\b(маргарин|margarine)', 'dairy.margarine'),
    (r'\b(ряженк)', 'dairy.ryazhenka'),
    (r'\b(простокваш)', 'dairy.prostokvasha'),
    (r'\b(айран)', 'dairy.ayran'),
    (r'\b(тан)', 'dairy.tan'),
    (r'\b(мацони|matsoni)', 'dairy.matsoni'),
    (r'\b(сгущен|condensed)', 'dairy.condensed'),
    (r'\b(мороженое|ice.*cream)', 'dairy.ice_cream'),
    (r'\b(сырок|glazed.*curd)', 'dairy.curd_snack'),
    (r'\b(пахта|buttermilk)', 'dairy.buttermilk'),
    (r'\b(молочн.*продукт|молокосодерж)', 'dairy.milk_product'),
    
    # === ОВОЩИ ===
    (r'\b(картофел|картошк|potato)', 'vegetables.potato'),
    (r'\b(морков|carrot)', 'vegetables.carrot'),
    (r'\b(лук|onion)(?!.*порей)', 'vegetables.onion'),
    (r'\b(лук.*порей|порей|leek)', 'vegetables.leek'),
    (r'\b(капуст|cabbage)(?!.*морск)(?!.*цветн)(?!.*брокол)(?!.*брюссел)(?!.*пекин)', 'vegetables.cabbage'),
    (r'\b(капуст.*цветн|цветн.*капуст|cauliflower)', 'vegetables.cauliflower'),
    (r'\b(брокол|broccoli)', 'vegetables.broccoli'),
    (r'\b(брюссел|brussels)', 'vegetables.brussels_sprouts'),
    (r'\b(пекинск|chinese.*cabbage|napa)', 'vegetables.chinese_cabbage'),
    (r'\b(помидор|томат|tomato)(?!.*паст)(?!.*соус)(?!.*кетчуп)', 'vegetables.tomato'),
    (r'\b(огурец|огурц|cucumber)(?!.*марин)(?!.*солен)', 'vegetables.cucumber'),
    (r'\b(огурец.*марин|огурц.*марин|корнишон|pickle)', 'vegetables.pickles'),
    (r'\b(перец|pepper)(?!.*чёрн)(?!.*красн.*молот)(?!.*черн)(?!.*халапен)', 'vegetables.pepper'),
    (r'\b(халапен|jalapeno)', 'vegetables.jalapeno'),
    (r'\b(баклажан|eggplant|aubergine)', 'vegetables.eggplant'),
    (r'\b(кабачок|кабачк|zucchini|courgette)', 'vegetables.zucchini'),
    (r'\b(свекл|свёкл|beet)', 'vegetables.beet'),
    (r'\b(чеснок|garlic)', 'vegetables.garlic'),
    (r'\b(имбир|ginger)', 'vegetables.ginger'),
    (r'\b(редис|radish)', 'vegetables.radish'),
    (r'\b(редьк|daikon)', 'vegetables.daikon'),
    (r'\b(репа|turnip)', 'vegetables.turnip'),
    (r'\b(сельдер|celery)', 'vegetables.celery'),
    (r'\b(шпинат|spinach)', 'vegetables.spinach'),
    # Салат - исключаем "для салата", "контейнер", "упаковка"
    (r'\b(салат|lettuce|руккол|arugula)(?!.*морск)(?!.*контейнер)(?!.*упаков)(?!.*для)', 'vegetables.salad'),
    (r'\b(укроп|dill)', 'vegetables.dill'),
    (r'\b(петрушк|parsley)', 'vegetables.parsley'),
    (r'\b(кинз|cilantro|coriander)', 'vegetables.cilantro'),
    (r'\b(базилик|basil)', 'vegetables.basil'),
    # Мята - исключаем чай с мятой
    (r'\b(мят|mint)(?!.*чай)', 'vegetables.mint'),
    (r'\b(горох|горошек|pea)(?!.*нут)', 'vegetables.peas'),
    (r'\b(нут|chickpea)', 'vegetables.chickpea'),
    (r'\b(фасол|bean)(?!.*стручк)', 'vegetables.beans'),
    (r'\b(фасол.*стручк|стручк.*фасол|green.*bean)', 'vegetables.green_beans'),
    # Кукуруза - исключаем "хлеб кукурузный", "мука"
    (r'\b(кукуруз|corn|маис)(?!.*хлеб)(?!.*мук)', 'vegetables.corn'),
    (r'\b(тыкв|pumpkin|squash)', 'vegetables.pumpkin'),
    # Грибы - исключаем "салфетки", "рисунок"
    (r'\b(грибы|гриб|mushroom|шампиньон|вешенк|лисичк|опят)(?!.*салфетк)(?!.*рисун)', 'vegetables.mushrooms'),
    # Оливки - исключаем "масло оливковое"
    (r'\b(оливк|olive)(?!.*масл)', 'vegetables.olives'),
    (r'\b(маслин)', 'vegetables.olives'),
    (r'\b(каперс|caper)', 'vegetables.capers'),
    (r'\b(артишок|artichoke)', 'vegetables.artichoke'),
    (r'\b(спарж|asparagus)', 'vegetables.asparagus'),
    (r'\b(авокадо|avocado)', 'vegetables.avocado'),
    
    # === ФРУКТЫ И ЯГОДЫ ===
    (r'\b(яблок|apple)', 'fruits.apple'),
    (r'\b(груш|pear)', 'fruits.pear'),
    (r'\b(апельсин|orange)', 'fruits.orange'),
    (r'\b(лимон|lemon)', 'fruits.lemon'),
    (r'\b(лайм|lime)', 'fruits.lime'),
    (r'\b(грейпфрут|grapefruit)', 'fruits.grapefruit'),
    (r'\b(мандарин|tangerine|mandarin)', 'fruits.tangerine'),
    (r'\b(банан|banana)', 'fruits.banana'),
    (r'\b(виноград|grape)', 'fruits.grape'),
    (r'\b(персик|peach)', 'fruits.peach'),
    (r'\b(абрикос|apricot)', 'fruits.apricot'),
    (r'\b(слив|plum)(?!.*масл)(?!.*сок)', 'fruits.plum'),
    (r'\b(вишн|черешн|cherry)', 'fruits.cherry'),
    (r'\b(клубник|strawberry)', 'fruits.strawberry'),
    (r'\b(малин|raspberry)', 'fruits.raspberry'),
    (r'\b(ежевик|blackberry)', 'fruits.blackberry'),
    (r'\b(черник|blueberry)', 'fruits.blueberry'),
    (r'\b(голубик|blueberry)', 'fruits.blueberry'),
    (r'\b(клюкв|cranberry)', 'fruits.cranberry'),
    (r'\b(брусник|lingonberry)', 'fruits.lingonberry'),
    (r'\b(смородин|currant)', 'fruits.currant'),
    (r'\b(крыжовник|gooseberry)', 'fruits.gooseberry'),
    (r'\b(киви|kiwi)', 'fruits.kiwi'),
    (r'\b(манго|mango)', 'fruits.mango'),
    (r'\b(ананас|pineapple)', 'fruits.pineapple'),
    (r'\b(папай|papaya)', 'fruits.papaya'),
    (r'\b(маракуй|passion.*fruit)', 'fruits.passion_fruit'),
    (r'\b(гранат|pomegranate)', 'fruits.pomegranate'),
    (r'\b(хурм|persimmon)', 'fruits.persimmon'),
    (r'\b(инжир|fig)', 'fruits.fig'),
    (r'\b(финик|date)', 'fruits.date'),
    (r'\b(курага|dried.*apricot)', 'fruits.dried_apricot'),
    (r'\b(изюм|raisin)', 'fruits.raisin'),
    (r'\b(чернослив|prune)', 'fruits.prune'),
    (r'\b(дын|melon)', 'fruits.melon'),
    (r'\b(арбуз|watermelon)', 'fruits.watermelon'),
    (r'\b(пюре.*фрукт|фрукт.*пюре|fruit.*puree)', 'fruits.puree'),
    
    # === ВЫПЕЧКА И ХЛЕБ ===
    (r'\b(хлеб|bread|батон|багет|baguette)', 'bakery.bread'),
    (r'\b(булочк|булка|bun|roll)', 'bakery.bun'),
    (r'\b(круассан|croissant)', 'bakery.croissant'),
    (r'\b(пирог|pie|tart)(?!.*пирож)', 'bakery.pie'),
    (r'\b(пирожок|пирожк)', 'bakery.piroshki'),
    (r'\b(пирожн|pastry|эклер|eclair)', 'bakery.pastry'),
    (r'\b(торт|cake)', 'bakery.cake'),
    (r'\b(кекс|muffin|cupcake)', 'bakery.muffin'),
    (r'\b(печень|cookie|biscuit)', 'bakery.cookie'),
    (r'\b(вафл|wafer|waffle)', 'bakery.waffle'),
    (r'\b(блин|pancake|crepe)', 'bakery.pancake'),
    (r'\b(оладь|fritter)', 'bakery.fritter'),
    (r'\b(сырник)', 'bakery.syrniki'),
    (r'\b(слойк|puff)', 'bakery.puff_pastry'),
    (r'\b(тест.*дрожж|дрожж.*тест|yeast.*dough)', 'bakery.yeast_dough'),
    (r'\b(тест.*слоен|слоен.*тест|puff.*dough)', 'bakery.puff_dough'),
    (r'\b(тесто|dough)', 'bakery.dough'),
    (r'\b(лаваш|lavash)', 'bakery.lavash'),
    (r'\b(лепешк|flatbread)', 'bakery.flatbread'),
    (r'\b(пита|pita)', 'bakery.pita'),
    (r'\b(тортилья|tortilla)', 'bakery.tortilla'),
    (r'\b(сухар|crouton|breadcrumb)', 'bakery.breadcrumbs'),
    (r'\b(панировк|breading)', 'bakery.breading'),
    
    # === КРУПЫ И МАКАРОНЫ ===
    (r'\b(рис|rice)', 'staples.rice'),
    (r'\b(гречк|гречнев|buckwheat)', 'staples.buckwheat'),
    (r'\b(овсян|овёс|oat)', 'staples.oats'),
    (r'\b(пшен|millet)', 'staples.millet'),
    (r'\b(пшениц|wheat)(?!.*мук)', 'staples.wheat'),
    (r'\b(ячмен|ячнев|barley|перловк)', 'staples.barley'),
    (r'\b(кукуруз.*круп|круп.*кукуруз|polenta)', 'staples.polenta'),
    (r'\b(манк|semolina)', 'staples.semolina'),
    (r'\b(кускус|couscous)', 'staples.couscous'),
    (r'\b(булгур|bulgur)', 'staples.bulgur'),
    (r'\b(киноа|quinoa)', 'staples.quinoa'),
    (r'\b(чечевиц|lentil)', 'staples.lentils'),
    (r'\b(макарон|паста|pasta|спагетти|spaghetti|пенне|penne|фузилли|fusilli|фарфалле|farfalle|лапш|noodle|лазань|lasagna|каннеллон|cannelloni|тальятелл|tagliatelle|феттуччин|fettuccine)', 'pasta.pasta'),
    (r'\b(вермишел|vermicelli)', 'pasta.vermicelli'),
    (r'\b(мука|flour)', 'staples.flour'),
    (r'\b(крахмал|starch)', 'staples.starch'),
    
    # === НАПИТКИ ===
    (r'\b(вода|water)(?!.*газ)(?!.*минерал)', 'beverages.water'),
    (r'\b(газ.*вода|вода.*газ|sparkling|минерал)', 'beverages.sparkling_water'),
    (r'\b(сок|juice)', 'beverages.juice'),
    (r'\b(нектар|nectar)', 'beverages.nectar'),
    (r'\b(морс|mors)', 'beverages.mors'),
    (r'\b(компот|compote)', 'beverages.compote'),
    (r'\b(кисель|kissel)', 'beverages.kissel'),
    (r'\b(чай|tea)', 'beverages.tea'),
    (r'\b(кофе|coffee)(?!.*сливк)', 'beverages.coffee'),
    (r'\b(какао|cocoa|горяч.*шоколад)', 'beverages.cocoa'),
    (r'\b(лимонад|lemonade)', 'beverages.lemonade'),
    (r'\b(кола|cola|пепси|pepsi|фанта|fanta|спрайт|sprite)', 'beverages.soda'),
    (r'\b(энергетик|energy.*drink|red.*bull|monster)', 'beverages.energy_drink'),
    (r'\b(квас|kvass)', 'beverages.kvass'),
    (r'\b(пиво|beer|лагер|lager|эль|ale)', 'beverages.beer'),
    (r'\b(вино|wine)(?!.*уксус)', 'beverages.wine'),
    (r'\b(шампанск|champagne|игрист)', 'beverages.champagne'),
    (r'\b(водка|vodka)', 'beverages.vodka'),
    (r'\b(коньяк|cognac|бренди|brandy)', 'beverages.cognac'),
    (r'\b(виски|whisky|whiskey)', 'beverages.whisky'),
    (r'\b(ром|rum)', 'beverages.rum'),
    (r'\b(джин|gin)', 'beverages.gin'),
    (r'\b(текила|tequila)', 'beverages.tequila'),
    (r'\b(ликёр|ликер|liqueur)', 'beverages.liqueur'),
    (r'\b(молок.*кокос|кокос.*молок|coconut.*milk)', 'beverages.coconut_milk'),
    (r'\b(молок.*соев|соев.*молок|soy.*milk)', 'beverages.soy_milk'),
    (r'\b(молок.*миндал|миндал.*молок|almond.*milk)', 'beverages.almond_milk'),
    (r'\b(молок.*овс|овс.*молок|oat.*milk)', 'beverages.oat_milk'),
    (r'\b(не.*молок|напиток.*раст)', 'beverages.plant_milk'),
    
    # === ПРИПРАВЫ И СОУСЫ ===
    (r'\b(соус|sauce)(?!.*томат)(?!.*соев)(?!.*тартар)(?!.*барбекю)(?!.*терияки)(?!.*чили)(?!.*песто)', 'condiments.sauce'),
    (r'\b(соус.*томат|томат.*соус|томат.*паст|паст.*томат|tomato.*sauce|tomato.*paste)', 'condiments.tomato_sauce'),
    (r'\b(соус.*соев|соев.*соус|soy.*sauce)', 'condiments.soy_sauce'),
    (r'\b(тартар|tartar)', 'condiments.tartar'),
    (r'\b(барбекю|bbq)', 'condiments.bbq'),
    (r'\b(терияки|teriyaki)', 'condiments.teriyaki'),
    (r'\b(чили.*соус|соус.*чили|chili.*sauce|sriracha)', 'condiments.chili_sauce'),
    (r'\b(песто|pesto)', 'condiments.pesto'),
    (r'\b(майонез|mayo)', 'condiments.mayo'),
    (r'\b(кетчуп|ketchup)', 'condiments.ketchup'),
    (r'\b(горчиц|mustard)', 'condiments.mustard'),
    (r'\b(хрен|horseradish)', 'condiments.horseradish'),
    (r'\b(васаби|wasabi)', 'condiments.wasabi'),
    (r'\b(уксус|vinegar)', 'condiments.vinegar'),
    (r'\b(соль|salt)(?!.*ван)', 'condiments.salt'),
    (r'\b(перец.*молот|молот.*перец|ground.*pepper|чёрн.*перец|черн.*перец|black.*pepper)', 'condiments.pepper'),
    (r'\b(специ|spice|приправ|seasoning)', 'condiments.spice'),
    (r'\b(корица|cinnamon)', 'condiments.cinnamon'),
    (r'\b(ваниль|vanilla)', 'condiments.vanilla'),
    (r'\b(карри|curry)', 'condiments.curry'),
    (r'\b(куркум|turmeric)', 'condiments.turmeric'),
    (r'\b(паприк|paprika)', 'condiments.paprika'),
    (r'\b(орегано|oregano)', 'condiments.oregano'),
    (r'\b(тимьян|thyme)', 'condiments.thyme'),
    (r'\b(розмарин|rosemary)', 'condiments.rosemary'),
    (r'\b(мускат|nutmeg)', 'condiments.nutmeg'),
    (r'\b(гвоздик|clove)', 'condiments.clove'),
    (r'\b(лавр.*лист|лист.*лавр|bay.*leaf)', 'condiments.bay_leaf'),
    (r'\b(кориандр|coriander)(?!.*зелен)', 'condiments.coriander'),
    (r'\b(зира|кумин|cumin)', 'condiments.cumin'),
    (r'\b(аджик|adjika)', 'condiments.adjika'),
    (r'\b(ткемал|tkemali)', 'condiments.tkemali'),
    (r'\b(сацебел|satsebeli)', 'condiments.satsebeli'),
    (r'\b(бульон|broth|bouillon)', 'condiments.broth'),
    
    # === МАСЛА ===
    (r'\b(масло.*подсолн|подсолн.*масло|sunflower.*oil)', 'oils.sunflower'),
    (r'\b(масло.*оливк|оливк.*масло|olive.*oil)', 'oils.olive'),
    (r'\b(масло.*кукуруз|кукуруз.*масло|corn.*oil)', 'oils.corn'),
    (r'\b(масло.*рапс|рапс.*масло|rapeseed|canola)', 'oils.rapeseed'),
    (r'\b(масло.*льнян|льнян.*масло|linseed|flaxseed)', 'oils.flaxseed'),
    (r'\b(масло.*кунжут|кунжут.*масло|sesame.*oil)', 'oils.sesame'),
    (r'\b(масло.*кокос|кокос.*масло|coconut.*oil)', 'oils.coconut'),
    (r'\b(масло.*фритюр|фритюр|frying.*oil)', 'oils.frying'),
    (r'\b(масло.*раст|раст.*масло|vegetable.*oil)', 'oils.vegetable'),
    
    # === КОНСЕРВЫ ===
    (r'\b(консерв|canned|конс\.)(?!.*горош)(?!.*кукуруз)(?!.*фасол)(?!.*рыб)(?!.*мяс)', 'canned.general'),
    (r'\b(горош.*конс|конс.*горош|canned.*pea)', 'canned.peas'),
    (r'\b(кукуруз.*конс|конс.*кукуруз|canned.*corn)', 'canned.corn'),
    (r'\b(фасол.*конс|конс.*фасол|canned.*bean)', 'canned.beans'),
    (r'\b(рыб.*конс|конс.*рыб|тушенк.*рыб|canned.*fish)', 'canned.fish'),
    (r'\b(мяс.*конс|конс.*мяс|тушенк|canned.*meat)', 'canned.meat'),
    (r'\b(шпрот|sprat)', 'canned.sprats'),
    (r'\b(сардин.*конс|конс.*сардин)', 'canned.sardines'),
    (r'\b(груздь|грузди)', 'canned.mushrooms'),
    (r'\b(опят.*марин|марин.*опят)', 'canned.mushrooms'),
    
    # === СЛАДОСТИ И ДЕСЕРТЫ ===
    (r'\b(шоколад|chocolate)(?!.*масл)(?!.*напит)(?!.*waffle)(?!.*стакан)', 'desserts.chocolate'),
    (r'\b(конфет|candy|карамел|caramel)', 'desserts.candy'),
    (r'\b(мармелад|marmalade|желе|jelly)', 'desserts.jelly'),
    (r'\b(зефир|marshmallow)', 'desserts.marshmallow'),
    (r'\b(пастил|pastila)', 'desserts.pastila'),
    (r'\b(халв|halva)', 'desserts.halva'),
    (r'\b(мёд|мед|honey)', 'desserts.honey'),
    (r'\b(джем|jam)', 'desserts.jam'),
    (r'\b(варень|preserves)', 'desserts.preserves'),
    (r'\b(сироп|syrup)', 'desserts.syrup'),
    # Сахар - исключаем "сахар порционный" (это staples)
    (r'\b(сахар|sugar)(?!.*порцион)(?!.*стик)', 'desserts.sugar'),
    (r'\b(подсластител|sweetener)', 'desserts.sweetener'),
    (r'\b(ореш|орех|nut|миндал|almond|фундук|hazelnut|грецк|walnut|кешью|cashew|фисташк|pistachio|арахис|peanut)', 'desserts.nuts'),
    (r'\b(семечк|seed|подсолнух)', 'desserts.seeds'),
    
    # === ЗАМОРОЗКА (только для замороженных полуфабрикатов без категории) ===
    # НЕ применять к мясу, рыбе, птице с "с/м" - у них есть своя категория!
    # (r'\b(заморож|frozen)', 'frozen'),  # ОТКЛЮЧЕНО - слишком агрессивно
    
    # === УПАКОВКА ===
    (r'\b(контейнер|container)(?!.*для)', 'packaging.container'),
    (r'\b(пакет|bag)(?!.*чай)', 'packaging.bag'),
    (r'\b(плёнк|пленк|film|wrap)(?!.*пищев)', 'packaging.film'),
    (r'\b(фольг|foil)', 'packaging.foil'),
    (r'\b(бумаг.*пергамент|пергамент)', 'packaging.parchment'),
    (r'\b(коробк|box)', 'packaging.box'),
    (r'\b(лоток|tray)', 'packaging.tray'),
    (r'\b(вакуум.*пакет|пакет.*вакуум)', 'packaging.vacuum_bag'),
    
    # === ОДНОРАЗОВАЯ ПОСУДА ===
    # Стакан - исключаем waffle, молоко и т.д.
    (r'\b(стакан|cup|стаканчик)(?!.*молок)(?!.*йогурт)(?!.*waffle)(?!.*black)', 'disposables.cups'),
    (r'\b(тарелк|plate|блюдц)', 'disposables.plates'),
    (r'\b(вилк|fork)', 'disposables.forks'),
    (r'\b(ложк|spoon)', 'disposables.spoons'),
    (r'\b(нож.*одноразов|одноразов.*нож|plastic.*knife)', 'disposables.knives'),
    # Салфетки - исключаем рисунки
    (r'\b(салфетк|napkin)(?!.*гриб)(?!.*рисун)', 'disposables.napkins'),
    (r'\b(перчатк|glove)', 'disposables.gloves'),
    (r'\b(трубочк|straw)', 'disposables.straws'),
    
    # === ДОБАВКИ ===
    (r'\b(дрожж|yeast)', 'additives.yeast'),
    (r'\b(разрыхлител|baking.*powder)', 'additives.baking_powder'),
    (r'\b(сода|baking.*soda)', 'additives.baking_soda'),
    (r'\b(желатин|gelatin)', 'additives.gelatin'),
    (r'\b(агар|agar)', 'additives.agar'),
    (r'\b(пектин|pectin)', 'additives.pectin'),
    (r'\b(красител|colorant|coloring)', 'additives.colorant'),
    (r'\b(ароматизатор|flavoring)', 'additives.flavoring'),
    (r'\b(загустител|thickener)', 'additives.thickener'),
    (r'\b(эмульгатор|emulsifier)', 'additives.emulsifier'),
    (r'\b(лимон.*кислот|citric.*acid)', 'additives.citric_acid'),
    
    # === ГОТОВЫЕ БЛЮДА ===
    (r'\b(пицц|pizza)', 'ready_meals.pizza'),
    (r'\b(суши|sushi|ролл|roll)', 'ready_meals.sushi'),
    (r'\b(суп|soup|борщ|borscht|щи|shchi|солянк|solyanka|рассольник|уха)', 'ready_meals.soup'),
    (r'\b(каш|porridge)(?!.*крупа)', 'ready_meals.porridge'),
    (r'\b(салат.*готов|готов.*салат)', 'ready_meals.salad'),
    (r'\b(сэндвич|sandwich|бургер|burger)', 'ready_meals.sandwich'),
    (r'\b(хот.*дог|hot.*dog)', 'ready_meals.hotdog'),
    (r'\b(шаурм|shawarma|дёнер|донер|doner)', 'ready_meals.shawarma'),
    
    # === ДЕТСКОЕ ПИТАНИЕ ===
    (r'\b(детск.*питан|питан.*детск|baby.*food)', 'baby_food.general'),
    (r'\b(детск.*пюре|пюре.*детск)', 'baby_food.puree'),
    (r'\b(детск.*каш|каш.*детск)', 'baby_food.porridge'),
    (r'\b(детск.*смес|смес.*детск|formula)', 'baby_food.formula'),
    
    # === ЯЙЦА ===
    # ВАЖНО: специфичные правила ПЕРЕД общими!
    (r'\b(перепел.*яйц|яйц.*перепел|quail.*egg)', 'eggs.quail'),
    (r'\b(яйц|egg)(?!.*пельм)(?!.*макар)', 'eggs.chicken'),
]

def classify_product(name: str) -> Optional[str]:
    """
    Классифицирует товар по названию.
    
    Returns: super_class или None если не удалось классифицировать
    """
    if not name:
        return None
    
    name_lower = name.lower()
    
    for pattern, category in CLASSIFICATION_RULES:
        if re.search(pattern, name_lower):
            return category
    
    return None


def classify_with_confidence(name: str) -> Tuple[Optional[str], float]:
    """
    Классифицирует с оценкой уверенности.
    
    Returns: (super_class, confidence 0.0-1.0)
    """
    if not name:
        return None, 0.0
    
    name_lower = name.lower()
    matches = []
    
    for pattern, category in CLASSIFICATION_RULES:
        if re.search(pattern, name_lower):
            matches.append(category)
    
    if not matches:
        return None, 0.0
    
    # Если только одно совпадение - высокая уверенность
    if len(matches) == 1:
        return matches[0], 1.0
    
    # Несколько совпадений - берём первое (более специфичное), но с меньшей уверенностью
    return matches[0], 0.7


def batch_classify(items: list) -> dict:
    """
    Массовая классификация.
    
    Returns: {item_id: super_class}
    """
    results = {}
    for item in items:
        item_id = item.get('id')
        name = item.get('name_raw') or item.get('name_norm', '')
        results[item_id] = classify_product(name)
    return results


if __name__ == '__main__':
    # Test
    test_names = [
        'Брусника см 1кг/12,5кг',
        'Молоко Клевер 6% 1л/12шт',
        'КРЕВЕТКИ очищенные с хвостиком',
        'Сыр Голландский 45% вес',
        'Филе куриное охлажденное',
        'Соус соевый Киккоман 150мл',
        'Масло подсолнечное рафинированное',
    ]
    
    print("Test classification:")
    for name in test_names:
        cat = classify_product(name)
        print(f"  {name[:40]}... → {cat}")
