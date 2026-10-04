const { PrismaClient } = require('@prisma/client');
const bcrypt = require('bcryptjs');
const prisma = new PrismaClient();

async function main() {
  const cashierPassword = process.env.BOOTSTRAP_CASHIER_PASSWORD;
  if (!cashierPassword || cashierPassword.length < 12) {
    throw new Error('BOOTSTRAP_CASHIER_PASSWORD must be configured with at least 12 characters');
  }

  const branch = await prisma.branch.upsert({
    where: { code: 'BR-001' },
    update: {},
    create: {
      name: 'Main Branch',
      location: 'Nairobi CBD',
      code: 'BR-001',
    },
  });

  const passwordHash = await bcrypt.hash(cashierPassword, 10);
  await prisma.user.upsert({
    where: { username: 'cashier1' },
    update: {},
    create: {
      username: 'cashier1',
      passwordHash,
      name: 'John Doe',
      role: 'CASHIER',
      branchId: branch.id,
    },
  });

  await prisma.product.createMany({
    data: [
      { name: 'Milk 1L', barcode: '111111', price: 100, costPrice: 80, stockLevel: 50, branchId: branch.id },
      { name: 'Bread 400g', barcode: '222222', price: 65, costPrice: 50, stockLevel: 100, branchId: branch.id },
      { name: 'Sugar 1kg', barcode: '333333', price: 210, costPrice: 180, stockLevel: 30, branchId: branch.id },
    ],
  });

  console.log('Seed data created!');
}

main()
  .catch((e) => console.error(e))
  .finally(async () => await prisma.$disconnect());
