import sys
import os
sys.path.append(os.getcwd())

# Import all models to check their types
try:
    from app.db.models.campaign import Campaign
    from app.db.models.platform_feed import PlatformFeed  
    from app.db.models.facebook_details import FacebookDetails
    from app.db.models.export_log import ExportLog
    from app.db.models.uploaded_image import UploadedImage
    
    print('🔍 Checking Model ID Types:')
    print('=' * 50)
    
    models = [
        ('Campaign', Campaign),
        ('PlatformFeed', PlatformFeed),
        ('FacebookDetails', FacebookDetails),
        ('ExportLog', ExportLog),
        ('UploadedImage', UploadedImage)
    ]
    
    all_correct = True
    for name, model in models:
        print(f'{name}:')
        for column in model.__table__.columns:
            if 'id' in column.name.lower():
                col_type = str(column.type)
                is_integer = 'INTEGER' in col_type.upper() or 'INT' in col_type.upper()
                status = '✅' if is_integer else '❌'
                print(f'   {status} {column.name}: {col_type}')
                if not is_integer:
                    all_correct = False
        print()
    
    if all_correct:
        print('🎉 ALL MODELS ARE USING INTEGER IDS!')
    else:
        print('⚠️ Some models still have wrong ID types')
        
except Exception as e:
    print(f'❌ Error importing models: {e}')
