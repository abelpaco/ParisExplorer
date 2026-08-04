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
