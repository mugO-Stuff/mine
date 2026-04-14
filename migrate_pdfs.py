#!/usr/bin/env python3
"""
Script para migrar PDFs antigos do disco para o banco de dados.
Use: python migrate_pdfs.py
"""

import os
import sys
from app import app, db, Comprovante, UPLOAD_COMPROVANTES_FOLDER

def migrate_pdfs_to_database():
    """Migra todos os PDFs do disco para o banco de dados."""
    
    # Procura PDFs no disco
    pdf_dir = os.path.join(app.static_folder, UPLOAD_COMPROVANTES_FOLDER)
    
    if not os.path.isdir(pdf_dir):
        print(f"❌ Diretório não encontrado: {pdf_dir}")
        return
    
    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print("✅ Nenhum PDF encontrado no disco para migrar.")
        return
    
    print(f"📁 Encontrados {len(pdf_files)} PDFs no disco")
    print(f"   Diretório: {pdf_dir}\n")
    
    migrated = 0
    skipped = 0
    errors = 0
    
    with app.app_context():
        for filename in pdf_files:
            filepath = os.path.join(pdf_dir, filename)
            
            try:
                # Procura Comprovante que referencia este arquivo
                comprovante = Comprovante.query.filter(
                    Comprovante.arquivo_comprovante.like(f'%{filename}%')
                ).first()
                
                if not comprovante:
                    print(f"⚠️  {filename}: Comprovante não encontrado no banco")
                    skipped += 1
                    continue
                
                # Se já tem dados no banco, pula
                if comprovante.arquivo_comprovante_dados:
                    print(f"⏭️  {filename}: Já migrado para o banco")
                    skipped += 1
                    continue
                
                # Lê o PDF do disco
                with open(filepath, 'rb') as f:
                    pdf_data = f.read()
                
                # Salva no banco
                comprovante.arquivo_comprovante_dados = pdf_data
                db.session.commit()
                
                print(f"✅ {filename}: Migrado ({len(pdf_data)} bytes)")
                migrated += 1
                
            except Exception as e:
                print(f"❌ {filename}: Erro - {str(e)}")
                db.session.rollback()
                errors += 1
    
    print(f"\n📊 Resultado:")
    print(f"   Migrados: {migrated}")
    print(f"   Pulados: {skipped}")
    print(f"   Erros: {errors}")
    
    if migrated > 0:
        print(f"\n💡 Próximo passo: Depois de validar, você pode deletar os PDFs do disco:")
        print(f"   rm -r {pdf_dir}")
        print(f"   ou apagar manualmente: {pdf_dir}")

if __name__ == '__main__':
    print("🔄 Iniciando migração de PDFs...\n")
    migrate_pdfs_to_database()
    print("\n✨ Concluído!\n")
