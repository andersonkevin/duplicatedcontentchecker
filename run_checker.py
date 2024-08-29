from duplicatedcontentchecker import ContentDuplicateChecker

checker = ContentDuplicateChecker(base_url="https://www.wixseo.io", max_depth=5)
checker.run()

