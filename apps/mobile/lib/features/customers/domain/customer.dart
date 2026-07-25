class CustomerProperty {
  final String id;
  final String addressLine1;
  final String city;
  final String state;
  final String zipCode;
  final String propertyType;

  CustomerProperty({
    required this.id,
    required this.addressLine1,
    required this.city,
    required this.state,
    required this.zipCode,
    required this.propertyType,
  });
}

class CustomerContact {
  final String id;
  final String name;
  final String email;
  final String phone;
  final String role;

  CustomerContact({
    required this.id,
    required this.name,
    required this.email,
    required this.phone,
    required this.role,
  });
}

class Customer {
  final String id;
  final String tenantId;
  final String name;
  final String companyName;
  final String phone;
  final String email;
  final String status;
  final List<String> tags;
  final List<CustomerProperty> properties;
  final List<CustomerContact> contacts;

  Customer({
    required this.id,
    required this.tenantId,
    required this.name,
    required this.companyName,
    required this.phone,
    required this.email,
    required this.status,
    required this.tags,
    required this.properties,
    required this.contacts,
  });
}
