"""
Basic tests for ParisExplorer automation system
"""

import os
import sys
import yaml
import json
from pathlib import Path

# Les rapports de test sont ponctues de « ✓ » et « ✗ ». Sur une console Windows
# (cp1252 par defaut), les afficher leve UnicodeEncodeError DANS le rapport lui-
# meme : la suite s'arretait au premier test, avant d'en executer un seul.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def test_config_loading():
    """Test configuration file loading"""
    print("Testing config loading...")
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        assert config is not None, "Config is None"
        assert 'schedule' in config, "Missing schedule config"
        assert 'youtube' in config, "Missing youtube config"
        assert 'content_sources' in config, "Missing content_sources config"
        
        print("✓ Config loading successful")
        return True
    except Exception as e:
        print(f"✗ Config loading failed: {e}")
        return False


def test_directory_structure():
    """Test required directories exist"""
    print("\nTesting directory structure...")
    
    required_dirs = [
        'content',
        'content/videos',
        'content/images',
        'content/metadata',
        'logs',
        'temp'
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✓ {dir_path} exists")
        else:
            print(f"✗ {dir_path} missing")
            all_exist = False
    
    return all_exist


def test_required_files():
    """Test required files exist"""
    print("\nTesting required files...")
    
    required_files = [
        'requirements.txt',
        'config.yaml',
        '.env.example',
        '.gitignore',
        'automation.py',
        'youtube_uploader.py',
        'content_manager.py',
        'scheduler.py'
    ]
    
    all_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✓ {file_path} exists")
        else:
            print(f"✗ {file_path} missing")
            all_exist = False
    
    return all_exist


def test_imports():
    """Test Python module imports"""
    print("\nTesting module imports...")
    
    modules = [
        ('yaml', 'PyYAML'),
        ('schedule', 'schedule'),
        ('dotenv', 'python-dotenv'),
        ('requests', 'requests'),
        ('PIL', 'Pillow'),
    ]
    
    all_imported = True
    for module_name, package_name in modules:
        try:
            __import__(module_name)
            print(f"✓ {package_name} imported successfully")
        except ImportError:
            print(f"✗ {package_name} not installed - run: pip install {package_name}")
            all_imported = False
    
    return all_imported


def test_content_structure():
    """Test content directory structure"""
    print("\nTesting content structure...")
    
    content_readme = Path('content/README.md')
    if content_readme.exists():
        print("✓ Content README exists")
    else:
        print("✗ Content README missing")
        return False
    
    example_json = Path('content/example_video.json')
    if example_json.exists():
        print("✓ Example metadata exists")
        
        try:
            with open(example_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert 'title' in data, "Missing title in example"
            assert 'description' in data, "Missing description in example"
            print("✓ Example metadata is valid JSON")
        except Exception as e:
            print(f"✗ Example metadata invalid: {e}")
            return False
    else:
        print("✗ Example metadata missing")
        return False
    
    return True


def test_gitignore():
    """Test .gitignore contains sensitive files"""
    print("\nTesting .gitignore...")
    
    with open('.gitignore', 'r', encoding='utf-8') as f:
        gitignore_content = f.read()
    
    sensitive_files = [
        '.env',
        'token.json',
        'client_secrets.json',
        '__pycache__'
    ]
    
    all_present = True
    for pattern in sensitive_files:
        if pattern in gitignore_content:
            print(f"✓ {pattern} in .gitignore")
        else:
            print(f"✗ {pattern} missing from .gitignore")
            all_present = False
    
    return all_present


def test_schedule_config():
    """Test schedule configuration is valid"""
    print("\nTesting schedule configuration...")
    
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    schedule_config = config.get('schedule', {})
    post_times = schedule_config.get('post_times', [])
    
    if not post_times:
        print("✗ No post times configured")
        return False
    
    print(f"✓ {len(post_times)} post times configured:")
    for time_str in post_times:
        print(f"  - {time_str}")
    
    timezone = schedule_config.get('timezone', '')
    print(f"✓ Timezone: {timezone}")
    
    return True


def test_video_creator_import():
    """Le module se charge et expose le catalogue des sujets."""
    print("\nTesting video_creator import...")
    try:
        from video_creator import ParisVideoCreator, registry_key  # noqa: F401
        assert registry_key("tour-eiffel", "fr") == "tour-eiffel:fr"
        print("✓ video_creator imported successfully")
        return True
    except Exception as e:
        print(f"✗ video_creator import failed: {e}")
        return False


def test_topics_are_loadable():
    """Les sujets YAML se chargent et sont complets."""
    print("\nTesting content/topics...")
    try:
        import topic_loader
        topics = topic_loader.load_topics()
        assert topics, "aucun sujet en status: ready dans content/topics"
        for topic in topics:
            assert "fr" in topic.langs, f"{topic.id}: bloc 'fr' manquant"
            assert topic.image_queries, f"{topic.id}: aucune requete d'image"
            for lang, text in topic.langs.items():
                assert text.title, f"{topic.id}[{lang}]: titre vide"
                assert text.word_count >= topic_loader.MIN_NARRATION_WORDS, (
                    f"{topic.id}[{lang}]: narration trop courte "
                    f"({text.word_count} mots)"
                )
        print(f"✓ {len(topics)} sujet(s) valide(s)")
        return True
    except Exception as e:
        print(f"✗ topics invalides: {e}")
        return False


def test_topic_catalogue_is_bilingual():
    """Le catalogue expose UN couple sujet/langue par langue configuree.

    C'est le point qui empeche la version anglaise de disparaitre : si la cle
    du registre oubliait la langue, publier le francais marquerait le sujet
    comme fait.
    """
    print("\nTesting bilingual catalogue...")
    try:
        from video_creator import ParisVideoCreator
        creator = ParisVideoCreator({"video_creator": {"languages": ["fr", "en"]}})
        catalogue = creator.get_available_topics()
        assert catalogue, "catalogue vide"

        names = [c["name"] for c in catalogue]
        assert len(names) == len(set(names)), "cles de registre en double"
        for candidate in catalogue:
            assert candidate["name"].endswith(f":{candidate['lang']}"), (
                f"la cle {candidate['name']} ne porte pas la langue"
            )
        langs = {c["lang"] for c in catalogue}
        assert langs == {"fr", "en"}, f"langues manquantes: {langs}"
        print(f"✓ {len(catalogue)} couple(s) sujet/langue, langues {sorted(langs)}")
        return True
    except Exception as e:
        print(f"✗ catalogue invalide: {e}")
        return False


def test_no_republication():
    """Un couple sujet/langue publie ne doit jamais etre repropose."""
    print("\nTesting anti-republication guard...")
    try:
        import tempfile
        from pathlib import Path as _Path
        from topic_registry import TopicRegistry
        from video_creator import ParisVideoCreator

        with tempfile.TemporaryDirectory() as tmp:
            registry = TopicRegistry(_Path(tmp) / "published.json")
            creator = ParisVideoCreator({}, registry=registry)
            catalogue = creator.get_available_topics()
            assert catalogue, "catalogue vide"

            first = catalogue[0]["name"]
            registry.mark_published(first, video_id="test123")
            remaining = [c["name"] for c in registry.remaining(catalogue)]
            assert first not in remaining, (
                f"{first} est deja publie mais reste eligible"
            )

            # Publier TOUT doit donner une liste vide, jamais un repli sur le
            # premier sujet : c'est le bug historique que ce garde-fou corrige.
            for candidate in catalogue:
                registry.mark_published(candidate["name"])
            assert registry.remaining(catalogue) == [], (
                "des sujets restent eligibles alors que tout est publie"
            )
        print("✓ garde anti-republication OK")
        return True
    except Exception as e:
        print(f"✗ anti-republication: {e}")
        return False


def test_video_creator_config():
    """config.yaml expose bien la section video_creator attendue."""
    print("\nTesting video_creator configuration...")
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        assert 'video_creator' in config, "Missing video_creator config section"
        vc = config['video_creator']
        for key in ('output_dir', 'languages', 'shorts', 'auto_generate'):
            assert key in vc, f"Missing video_creator.{key}"
        assert vc['languages'], "video_creator.languages est vide"
        print(
            f"✓ video_creator config valid "
            f"(output_dir={vc['output_dir']}, languages={vc['languages']})"
        )
        return True
    except Exception as e:
        print(f"✗ video_creator config test failed: {e}")
        return False


def test_card_legibility():
    """Une carte sur fond BLANC doit rester lisible.

    C'est le test qui manquait. Le voile suivait la position absolue dans
    l'image avec une courbe creusee : a mi-hauteur il n'etait opaque qu'a 22 %
    meme pousse au maximum. Sur une carte carree, dont le texte commence vers
    la moitie, la boucle de renforcement mesurait bien mais ne pouvait rien
    assombrir. Le rendu restait techniquement valide et visuellement illisible.

    On verifie donc le RESULTAT : la zone de texte doit finir sombre.
    """
    print("\nTesting card legibility on a white background...")
    try:
        import tempfile
        from pathlib import Path as _Path

        from PIL import Image

        import visual_cards

        with tempfile.TemporaryDirectory() as tmp:
            work = _Path(tmp)
            white = work / "blanc.png"
            Image.new("RGB", (1600, 1600), (255, 255, 255)).save(white)

            for fmt in visual_cards.CARD_FORMATS:
                # On lit la mesure que le rendu a faite SOUS LE TEXTE. Mesurer
                # nous-memes une bande arbitraire raterait le defaut : le bug
                # d'origine touchait le haut du bloc de texte, pas le bas de la
                # carte, et une bande trop basse le declarait sain.
                rendered = visual_cards.render_card(
                    white,
                    "Une phrase posee sur un fond entierement blanc, le pire cas.",
                    work / f"{fmt}.png",
                    fmt=fmt,
                    eyebrow="Monument",
                )
                assert rendered.path.exists(), f"{fmt}: aucun fichier produit"
                assert rendered.is_legible, (
                    f"{fmt}: luminosite {rendered.text_luminance:.0f} sous le texte "
                    f"(max {visual_cards.MAX_TEXT_AREA_LUMINANCE}) — texte blanc "
                    f"illisible malgre un voile a {rendered.scrim_strength:.2f}"
                )
                print(
                    f"  ✓ {fmt}: luminosite {rendered.text_luminance:.0f} "
                    f"(voile {rendered.scrim_strength:.2f}, police {rendered.font_size})"
                )
        return True
    except Exception as e:
        print(f"✗ lisibilite des cartes: {e}")
        return False


def test_card_still_and_motion_agree():
    """Carte fixe et carte animée doivent poser le texte au MÊME endroit.

    L'animation dessine le texte sur un calque transparent, séparé du fond qui
    défile. Si la mise en page divergeait, une série mêlant fixes et animées se
    lirait comme deux gabarits différents — un défaut qui ne se voit qu'en
    regardant les deux côte à côte, donc jamais.

    Ce test ne rend aucune vidéo : il compare les mises en page et vérifie que
    le calque de texte est bien transparent là où il n'y a rien.
    """
    print("\nTesting still/motion layout agreement...")
    try:
        from PIL import Image

        import visual_cards

        import tempfile
        from pathlib import Path as _Path

        text = "Une phrase de longueur ordinaire pour caler la mise en page."
        with tempfile.TemporaryDirectory() as tmp:
            photo = _Path(tmp) / "fond.png"
            Image.new("RGB", (2200, 1400), (70, 90, 120)).save(photo)

            for fmt, size in visual_cards.CARD_FORMATS.items():
                still = visual_cards._layout(size, text, "Monument")
                canvas, overlay, motion, _, _ = visual_cards._motion_layers(
                    photo, text, fmt=fmt, eyebrow="Monument"
                )

                # Le piège : calculer la mise en page sur la toile élargie.
                assert motion.text_top == still.text_top, (
                    f"{fmt}: texte à y={motion.text_top} en animé contre "
                    f"{still.text_top} en fixe — mise en page calculée sur la "
                    f"toile au lieu du cadre ?"
                )
                assert motion.lines == still.lines, f"{fmt}: découpage des lignes différent"
                assert motion.font.size == still.font.size, f"{fmt}: police différente"
                assert overlay.size == size, f"{fmt}: calque de texte hors format"
                assert canvas.width > size[0], (
                    f"{fmt}: le fond ne déborde pas du cadre — aucun mouvement possible"
                )

                alpha = overlay.getchannel("A").getextrema()
                assert alpha[0] == 0, f"{fmt}: le calque de texte n'est pas transparent"
                assert alpha[1] == 255, f"{fmt}: le calque de texte est vide"
                print(
                    f"  ✓ {fmt}: texte à y={still.text_top}, "
                    f"course de {canvas.width - size[0]} px"
                )
        return True
    except Exception as e:
        print(f"✗ accord fixe/animé: {e}")
        return False


def test_card_labels():
    """Les categories s'affichent avec leurs accents et dans la langue."""
    print("\nTesting card category labels...")
    try:
        from visual_cards import category_label

        assert category_label("decouverte", "fr") == "Découverte"
        assert category_label("decouverte", "en") == "Discover"
        assert category_label("economie", "fr") == "Économie"
        # Une categorie inconnue passe telle quelle : mieux vaut une etiquette
        # imparfaite qu'une carte sans reperage.
        assert category_label("gastronomie", "fr") == "gastronomie"
        print("✓ libellés de catégorie corrects")
        return True
    except Exception as e:
        print(f"✗ libellés de catégorie: {e}")
        return False


def test_lieux_are_loadable():
    """Chaque lieu de content/lieux/ est valide : type, scene, 2 langues."""
    print("\nTesting lieu subjects...")
    try:
        import lieu_topics

        lieux = lieu_topics.load_lieux()
        assert lieux, "aucun lieu charge depuis content/lieux/"
        ok = True
        for lieu in lieux:
            for lang in ("fr", "en"):
                if lang not in lieu.langs:
                    print(f"✗ {lieu.id}: pas de textes '{lang}'")
                    ok = False
                    continue
                textes = lieu.textes(lang)
                assert len(textes.anecdote) == 2, \
                    f"{lieu.id}[{lang}]: anecdote != 2 lignes"
            print(f"✓ {lieu.id} ({lieu.type} -> {lieu.style}, scene {lieu.scene})")
        return ok
    except Exception as e:
        print(f"✗ lieux: {e}")
        return False


def test_lieu_scenes_render_valid_svg():
    """Chaque scene enregistree compose un SVG autonome et bien forme."""
    print("\nTesting lieu scenes...")
    try:
        import xml.etree.ElementTree as ET

        import lieu_style

        assert lieu_style.SCENES, "aucune scene enregistree"
        for nom, scene in sorted(lieu_style.SCENES.items()):
            svg = lieu_style.composer(
                nom, ["Ligne de test un", "et ligne de test deux."],
                "TEST", "fr",
            )
            ET.fromstring(svg)  # bien forme, sinon ParseError
            assert svg.startswith("<svg"), f"{nom}: racine inattendue"
            assert "<style" not in svg and "<script" not in svg, \
                f"{nom}: le SVG doit rester autonome (presentation inline)"
            assert "Ligne de test un" in svg, f"{nom}: anecdote absente"
            print(f"✓ scene {nom} [{scene.style}] : SVG bien forme")
        # L'anecdote est une cesure editoriale : 2 lignes, ni plus ni moins.
        try:
            lieu_style.composer("villette", ["une seule ligne"], "T", "fr")
            print("✗ une anecdote d'une ligne aurait du etre refusee")
            return False
        except lieu_style.LieuStyleError:
            pass
        return True
    except Exception as e:
        print(f"✗ scenes de lieux: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 50)
    print("ParisExplorer Automation System Tests")
    print("=" * 50)
    
    tests = [
        test_required_files,
        test_directory_structure,
        test_config_loading,
        test_schedule_config,
        test_content_structure,
        test_gitignore,
        test_imports,
        test_video_creator_import,
        test_topics_are_loadable,
        test_topic_catalogue_is_bilingual,
        test_no_republication,
        test_card_legibility,
        test_card_still_and_motion_agree,
        test_card_labels,
        test_video_creator_config,
        test_lieux_are_loadable,
        test_lieu_scenes_render_valid_svg,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 50)
    
    if all(results):
        print("\n✓ All tests passed! System is ready.")
        print("\nNext steps:")
        print("1. Setup YouTube API credentials (see SETUP.md)")
        print("2. Place content in content/ directory")
        print("3. Run: python automation.py --mode channel-info")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix issues above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
