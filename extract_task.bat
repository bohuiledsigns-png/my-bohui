@echo off
cd /d D:\Bohui_Global_Push
echo Starting extraction at %DATE% %TIME% > D:\Bohui_Global_Push\extract_log.txt
python -c "import tarfile; f=tarfile.open('GLOWFORGE_CRM_migration.tar.gz','r:gz'); f.extractall(path='GLOWFORGE_CRM'); f.close(); print('EXTRACTION_OK')" >> D:\Bohui_Global_Push\extract_log.txt 2>&1
echo Finished at %DATE% %TIME% >> D:\Bohui_Global_Push\extract_log.txt
