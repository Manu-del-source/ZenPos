const express = require('express');
const router = express.Router();
const inventoryController = require('../controllers/inventory.controller');
const auth = require('../middleware/auth.middleware');

const checkRole = require('../middleware/role.middleware');

const { body } = require('express-validator');
const validate = require('../middleware/validate.middleware');

router.get('/products', auth, inventoryController.getProducts);
router.get('/products/:barcode', auth, inventoryController.getProductByBarcode);

router.post('/products', 
  auth, 
  checkRole(['ADMIN']),
  [
    body('name').notEmpty().trim().escape(),
    body('barcode').isAlphanumeric().withMessage('Barcode must be alphanumeric'),
    body('price').isDecimal({ min: 0 }),
    body('costPrice').isDecimal({ min: 0 }),
    body('stockLevel').isInt({ min: 0 }),
    body('branchId').isUUID(),
  ],
  validate,
  inventoryController.upsertProduct
);

router.patch('/products/:id', 
  auth, 
  checkRole(['ADMIN']),
  [
    body('name').optional().trim().escape(),
    body('price').optional().isDecimal({ min: 0 }),
    body('stockLevel').optional().isInt({ min: 0 }),
  ],
  validate,
  inventoryController.updateProduct
);
router.delete('/products/:id', auth, checkRole(['ADMIN']), inventoryController.deleteProduct);


module.exports = router;
