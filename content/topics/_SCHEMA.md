# Format d'un sujet ParisExplorer

Un sujet = un fichier YAML dans `content/topics/`. Un fichier par sujet, pour
qu'ajouter du contenu ne demande jamais de toucher au code Python.

C'est ce qui remplace la liste `PARIS_TOPICS` codee en dur : elle plafonnait la
chaine a 8 videos, apres quoi le pipeline rebouclait sur le premier sujet.

## Regles

- **`id`** : identifiant stable en kebab-case. C'est la CLE du registre
  `content/metadata/published_topics.json` — ne jamais le renommer apres
  publication, sinon le sujet redeviendrait eligible et serait republie.
- **Bilingue obligatoire** : les blocs `fr` et `en` doivent tous deux exister.
  Une seule production visuelle sert aux deux langues ; seules la voix off et
  les metadonnees changent.
- **`narration`** : 350 a 450 mots pour viser 2 a 3 minutes. En dessous de 300,
  la video sera trop courte pour le format cible.
- **`image_queries`** : requetes envoyees a Wikimedia Commons. Prevoir 4 a 6
  requetes variees (angles, saisons, details) pour eviter un diaporama
  monotone. Les requetes en anglais donnent generalement plus de resultats.
- **`status`** : `draft` tant que la narration n'est pas relue. Le pipeline
  n'utilise QUE les sujets en `ready`.

## Exemple minimal

```yaml
id: tour-eiffel
category: monument          # monument | histoire | decouverte
status: ready               # draft | ready

image_queries:
  - "Eiffel Tower Paris"
  - "Tour Eiffel nuit illumination"
  - "Eiffel Tower construction 1889"

fr:
  title: "La Tour Eiffel, le symbole de Paris"
  subtitle: "Le symbole de Paris"
  narration: |
    (350-450 mots, ton documentaire, phrases courtes lisibles a voix haute)
  tags: ["Tour Eiffel", "Paris", "Monument"]

en:
  title: "The Eiffel Tower, the symbol of Paris"
  subtitle: "The symbol of Paris"
  narration: |
    (meme contenu, redige en anglais naturel — pas une traduction mot a mot)
  tags: ["Eiffel Tower", "Paris", "Landmark"]
```

## Sujets a date anniversaire (facultatif)

Un champ `anchor_date: "MM-JJ"` fait du sujet un « ce jour-la a Paris » : le
planificateur ne le place QUE ce jour-la, chaque annee, et il y passe en tete
des creneaux. Publie un autre jour, un anniversaire perd tout son sens — c'est
pourquoi la contrainte est stricte.

```yaml
id: liberation-paris
anchor_date: "08-25"      # 25 aout : reddition allemande, Paris libere
```

Deux consequences a connaitre :

- **Produire AVANT la date.** Un sujet ancre dont la video n'existe pas le
  jour J attend l'annee suivante. Verifier le calendrier de production une
  semaine avant chaque ancre.
- **La categorie `actualite` existe** pour ces sujets : l'angle reste
  l'Histoire, mais l'accroche est le jour anniversaire.

## Un sujet est un ANGLE, pas un monument

C'est la regle la plus importante du catalogue.

Un monument ne donne pas un sujet : il en donne plusieurs, selon l'angle qu'on
prend. La Tour Eiffel, c'est le chantier et ses contraintes. C'est aussi ses
chiffres. C'est aussi la vie de l'ingenieur qui l'a signee, sa disgrace et sa
seconde carriere. Trois sujets, trois recits, aucun doublon.

En pratique, l'identifiant porte l'angle :

```
tour-eiffel            l'histoire du monument
gustave-eiffel         l'homme, sa chute et sa revanche
tour-eiffel-chantier   les deux ans de construction, vus du sol
```

Interet direct : dix monuments a trois angles font trente sujets, pas dix. Un
catalogue se creuse plutot qu'il ne s'etale, et c'est ce qui donne a une chaine
une voix reconnaissable — on ne raconte pas ce qu'un guide raconte deja.

Deux garde-fous :

- **Chaque angle doit tenir seul.** Si le spectateur a besoin d'avoir vu l'autre
  video pour comprendre celle-ci, ce n'est pas un angle, c'est une deuxieme
  partie.
- **Pas de fait recycle en tete.** Deux angles peuvent partager un fait au
  passage, jamais leur accroche : c'est elle qui fait l'impression de deja-vu.

## Cartes visuelles (facultatif)

Chaque bloc de langue accepte un bloc `cards` : les accroches des publications
image. Sans lui, les cartes sont decoupees dans la narration — ca marche, mais
une phrase ecrite pour la voix off n'est pas une phrase ecrite pour l'image.

```yaml
fr:
  title: "..."
  narration: |
    ...
  cards:
    - "Elle devait disparaitre au bout de vingt ans."
    - "Deux millions et demi de rivets, poses un par un."
```

Viser 45 a 165 caracteres : en dessous ca ne dit rien, au-dessus ca ne se lit
plus sur un telephone. Une accroche par carte, dans l'ordre de lecture.

## Sujets pieges

Le filtre de licence protege contre une image mal licenciee. Il ne protege PAS
contre une image bien licenciee dont le SUJET est protege. Le monument peut
etre dans le domaine public alors que ce qu'on voit dessus ne l'est pas.

- **Tour Eiffel de nuit** : la structure est libre, mais la mise en lumiere
  creee par Pierre Bideau en 1985 est une oeuvre a part entiere. La SETE exige
  une autorisation pour tout usage commercial. Sur une chaine monetisee, ne
  jamais demander de vue nocturne de la tour.
- **Architecture recente** : la France n'a pas de « liberte de panorama »
  commerciale. Un batiment dont l'architecte est mort il y a moins de 70 ans
  reste protege (Pyramide du Louvre, Fondation Louis Vuitton, Philharmonie...).
- **Oeuvres exposees** : sculptures et fresques recentes visibles dans la rue
  suivent la meme regle que les batiments.

Regle pratique : si l'element marquant de l'image date d'apres 1950, se poser
la question avant d'ecrire la requete.

## A savoir sur les images

Les images viennent de Wikimedia Commons. La plupart sont sous licence CC BY ou
CC BY-SA : **le credit est une obligation legale**, pas une politesse. Le
pipeline collecte auteur + licence pour chaque image et les injecte
automatiquement en fin de description YouTube. Ne jamais retirer ce bloc.
